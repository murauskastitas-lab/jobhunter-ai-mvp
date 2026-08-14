import io, os, re, json, sqlite3, secrets, urllib.request, ssl
from datetime import datetime, timezone
from flask import Flask, render_template, request, jsonify, session
from dotenv import load_dotenv
from openai import OpenAI
from pypdf import PdfReader
from docx import Document
load_dotenv()
app=Flask(__name__); app.secret_key=os.getenv('FLASK_SECRET_KEY',secrets.token_hex(32)); app.config['MAX_CONTENT_LENGTH']=8*1024*1024
DB_PATH=os.getenv('DATABASE_PATH','jobhunter.db'); OPENAI_API_KEY=os.getenv('OPENAI_API_KEY',''); OPENAI_MODEL=os.getenv('OPENAI_MODEL','gpt-5-mini'); client=OpenAI(api_key=OPENAI_API_KEY) if OPENAI_API_KEY else None

def db():
 c=sqlite3.connect(DB_PATH); c.row_factory=sqlite3.Row; return c

def init_db():
 c=db(); c.execute('CREATE TABLE IF NOT EXISTS profiles (id TEXT PRIMARY KEY, profile_json TEXT NOT NULL, created_at TEXT NOT NULL)'); c.execute('CREATE TABLE IF NOT EXISTS opportunities (id TEXT PRIMARY KEY, profile_id TEXT NOT NULL, title TEXT, company TEXT, location TEXT, url TEXT, source TEXT, score INTEGER, reason TEXT, created_at TEXT NOT NULL)'); c.execute('CREATE TABLE IF NOT EXISTS feedback (id TEXT PRIMARY KEY, name TEXT, rating INTEGER, message TEXT, created_at TEXT NOT NULL)'); c.commit(); c.close()
init_db()

def extract_cv(file):
 if not file or not file.filename: raise ValueError('Please upload a CV.')
 name=file.filename.lower(); data=file.read()
 if name.endswith('.pdf'): text='\n'.join(p.extract_text() or '' for p in PdfReader(io.BytesIO(data)).pages)
 elif name.endswith('.docx'): text='\n'.join(p.text for p in Document(io.BytesIO(data)).paragraphs)
 elif name.endswith('.txt'): text=data.decode('utf-8',errors='ignore')
 else: raise ValueError('Use PDF, DOCX or TXT.')
 text=re.sub(r'\n{3,}','\n\n',text).strip()
 if len(text)<80: raise ValueError('The CV has too little readable text. If it is a scanned PDF, use a text-based PDF or OCR first.')
 return text[:50000]

def ai_json(instructions,prompt):
 if not client: raise RuntimeError('OPENAI_API_KEY is not configured in Railway Variables.')
 r=client.responses.create(model=OPENAI_MODEL,instructions=instructions,input=prompt,text={'format':{'type':'json_object'}},store=False); return json.loads(r.output_text)

def parse_profile(cv_text):
 shape={'first_name':'','last_name':'','email':'','phone':'','location':'','job_titles':[],'years_experience':0,'skills':[],'languages':[],'education':[],'work_experience':[],'missing_required':[],'profile_ready':False}
 return ai_json('You are a careful CV parser. Use only facts supported by the CV.',f'''Extract a truthful candidate profile. Never invent information. Required: first_name, last_name, email, phone, and at least one work_experience item. Missing/unclear required fields go in missing_required. Set profile_ready=true only when complete. Return JSON exactly like this: {json.dumps(shape)}\n\nCV:\n{cv_text}''')

def fetch_json(url):
 req=urllib.request.Request(url,headers={'User-Agent':'JobHunterAI/1.0'}); 
 with urllib.request.urlopen(req,timeout=20,context=ssl.create_default_context()) as r: return json.loads(r.read().decode('utf-8',errors='ignore'))

def discover_jobs(location,remote,titles):
 jobs=[]
 try:
  data=fetch_json('https://www.arbeitnow.com/api/job-board-api')
  for j in data.get('data',[]):
   hay=' '.join([j.get('title',''),j.get('description',''),j.get('company_name',''),j.get('location','')]).lower()
   if titles and not any(t.lower() in hay for t in titles): continue
   if location and not remote and location.lower() not in hay: continue
   jobs.append({'title':j.get('title',''),'company':j.get('company_name',''),'location':j.get('location',''),'url':j.get('url',''),'source':'Arbeitnow'})
 except Exception as e: app.logger.warning('Arbeitnow search failed: %s',e)
 if remote:
  try:
   data=fetch_json('https://remotive.com/api/remote-jobs')
   for j in data.get('jobs',[]):
    hay=' '.join([j.get('title',''),j.get('description',''),j.get('company_name',''),j.get('candidate_required_location','')]).lower()
    if titles and not any(t.lower() in hay for t in titles): continue
    if location and location.lower() not in hay and location.lower() not in ('worldwide',''): continue
    jobs.append({'title':j.get('title',''),'company':j.get('company_name',''),'location':j.get('candidate_required_location','Remote'),'url':j.get('url',''),'source':'Remotive'})
  except Exception as e: app.logger.warning('Remotive search failed: %s',e)
 seen=set(); out=[]
 for j in jobs:
  k=(j['title'].lower(),j['company'].lower(),j['url'])
  if k not in seen: seen.add(k); out.append(j)
 return out[:120]

def match_job(profile,job): return ai_json('You are a conservative recruitment matching engine. Never invent candidate qualifications.',f'''Score this job for the candidate from 0 to 100. Candidate: {json.dumps(profile)} Job: {json.dumps(job)} Return JSON: {{"score":0,"reason":"one short truthful reason"}}''')
def application_draft(profile,job): return ai_json('You write concise professional job applications using only supported facts.',f'''Create a short truthful application email. Candidate: {json.dumps(profile)} Job: {json.dumps(job)} Do not invent facts. Return JSON: {{"subject":"","body":""}}''')

@app.get('/')
def home(): return render_template('index.html')
@app.get('/health')
def health(): return jsonify(status='ok',service='jobhunter-ai')
@app.post('/api/profile')
def profile():
 try:
  p=parse_profile(extract_cv(request.files.get('cv'))); pid=secrets.token_urlsafe(16); c=db(); c.execute('INSERT INTO profiles VALUES (?,?,?)',(pid,json.dumps(p),datetime.now(timezone.utc).isoformat())); c.commit(); c.close(); session['profile_id']=pid; return jsonify({'profile_id':pid,**p})
 except Exception as e: app.logger.exception('profile scan failed'); return jsonify(error=str(e)),400
@app.post('/api/search')
def search():
 try:
  pid=session.get('profile_id'); row=db().execute('SELECT profile_json FROM profiles WHERE id=?',(pid,)).fetchone() if pid else None
  if not row: return jsonify(error='Upload your CV first.'),400
  p=json.loads(row['profile_json']); location=request.form.get('location','').strip(); remote=request.form.get('remote')=='true'; jobs=discover_jobs(location,remote,p.get('job_titles',[])); out=[]; c=db()
  for j in jobs[:60]:
   m=match_job(p,j); score=max(0,min(100,int(m.get('score',0)))); oid=secrets.token_urlsafe(16); c.execute('INSERT INTO opportunities VALUES (?,?,?,?,?,?,?,?,?,?)',(oid,pid,j['title'],j['company'],j['location'],j['url'],j['source'],score,m.get('reason',''),datetime.now(timezone.utc).isoformat())); out.append({'id':oid,**j,'score':score,'reason':m.get('reason','')})
  c.commit(); c.close(); out.sort(key=lambda x:x['score'],reverse=True); return jsonify(opportunities=out[:50],count=len(out))
 except Exception as e: app.logger.exception('job search failed'); return jsonify(error=str(e)),400
@app.post('/api/draft')
def draft():
 try:
  pid=session.get('profile_id'); oid=request.form.get('opportunity_id'); r=db().execute('SELECT * FROM opportunities WHERE id=? AND profile_id=?',(oid,pid)).fetchone(); p=db().execute('SELECT profile_json FROM profiles WHERE id=?',(pid,)).fetchone()
  if not r or not p: return jsonify(error='Opportunity not found.'),404
  return jsonify(**application_draft(json.loads(p['profile_json']),dict(r)))
 except Exception as e: return jsonify(error=str(e)),400
@app.post('/api/chat')
def chat():
 try:
  payload=request.get_json(silent=True) or {}; message=(payload.get('message') or request.form.get('message','')).strip()
  if not message: return jsonify(error='Please type a question.'),400
  if len(message)>1500: return jsonify(error='Question is too long.'),400
  profile=''; pid=session.get('profile_id')
  if pid:
   row=db().execute('SELECT profile_json FROM profiles WHERE id=?',(pid,)).fetchone()
   if row: profile=json.loads(row['profile_json'])
  instructions='''You are JobHunter AI, the friendly AI assistant on a job-search website. Start conversations warmly. Your core mission is to help people find work with less hassle. Explain the product simply: 1) the user drops their CV, 2) you check the CV/profile for essential information, 3) the user chooses a country or remote search, 4) JobHunter AI searches relevant public job listings and compares them with the profile, 5) it prepares personalized application drafts for suitable jobs. Be enthusiastic but professional, never guarantee employment, never claim a job application was submitted unless the system confirms it, and never invent job sources or capabilities. If the user seems unsure, offer to give them a simple step-by-step guide for finding and applying to jobs. If they ask about their CV, give practical advice. Keep answers conversational and fairly short.'''
  answer=ai_json(instructions,f'''The website tagline is: "Just drop your CV. Let us cook." The user is talking to the assistant because they want help with job seeking. Candidate profile if available: {json.dumps(profile)} User question: {message} Return JSON: {{"answer":"your natural conversational answer"}}''')
  return jsonify(answer=answer.get('answer',''))
 except Exception as e: app.logger.exception('chat failed'); return jsonify(error=str(e)),400
@app.post('/api/feedback')
def feedback():
 try:
  name=request.form.get('name','').strip()[:80]; message=request.form.get('message','').strip()[:1000]; rating=max(1,min(5,int(request.form.get('rating','5'))))
  if not message: return jsonify(error='Please write a short message.'),400
  c=db(); c.execute('INSERT INTO feedback VALUES (?,?,?,?,?)',(secrets.token_urlsafe(12),name,rating,message,datetime.now(timezone.utc).isoformat())); c.commit(); c.close(); return jsonify(ok=True)
 except Exception as e: return jsonify(error=str(e)),400
@app.errorhandler(413)
def too_large(_): return jsonify(error='CV is too large. Maximum 8 MB.'),413
if __name__=='__main__': app.run(host='0.0.0.0',port=int(os.getenv('PORT','5000')))
