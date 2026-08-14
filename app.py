import io, os, re, json, sqlite3, secrets, urllib.request, ssl
from datetime import datetime, timezone
from flask import Flask, render_template, request, jsonify, session
from dotenv import load_dotenv
from openai import OpenAI
from pypdf import PdfReader
from docx import Document

load_dotenv()
app = Flask(__name__)
app.secret_key = os.getenv('FLASK_SECRET_KEY', secrets.token_hex(32))
app.config['MAX_CONTENT_LENGTH'] = 8 * 1024 * 1024
DB_PATH = os.getenv('DATABASE_PATH', 'jobhunter.db')
OPENAI_API_KEY = os.getenv('OPENAI_API_KEY', '')
OPENAI_MODEL = os.getenv('OPENAI_MODEL', 'gpt-5-mini')
client = OpenAI(api_key=OPENAI_API_KEY, timeout=20.0, max_retries=0) if OPENAI_API_KEY else None

def db():
    c = sqlite3.connect(DB_PATH); c.row_factory = sqlite3.Row; return c

def init_db():
    c=db(); c.execute('CREATE TABLE IF NOT EXISTS profiles (id TEXT PRIMARY KEY, profile_json TEXT NOT NULL, created_at TEXT NOT NULL)'); c.execute('CREATE TABLE IF NOT EXISTS opportunities (id TEXT PRIMARY KEY, profile_id TEXT NOT NULL, title TEXT, company TEXT, location TEXT, url TEXT, source TEXT, score INTEGER, reason TEXT, created_at TEXT NOT NULL)'); c.execute('CREATE TABLE IF NOT EXISTS feedback (id TEXT PRIMARY KEY, name TEXT, rating INTEGER, message TEXT, created_at TEXT NOT NULL)'); c.commit(); c.close()
init_db()

def clean_text(text):
    text=text.replace('\x00',' '); text=re.sub(r'[ \t]+',' ',text); text=re.sub(r'\n{3,}','\n\n',text); return text.strip()

def pdf_ocr(data):
    try:
        import pytesseract
        from pdf2image import convert_from_bytes
        pages=convert_from_bytes(data,dpi=220,fmt='png',thread_count=1)
        return clean_text('\n'.join(pytesseract.image_to_string(p,config='--psm 3') for p in pages[:12]))
    except Exception as e:
        app.logger.warning('OCR fallback failed: %s',e); return ''

def extract_cv(file):
    if not file or not file.filename: raise ValueError('Please upload a CV.')
    name=file.filename.lower(); data=file.read()
    if name.endswith('.pdf'):
        text=clean_text('\n'.join(p.extract_text() or '' for p in PdfReader(io.BytesIO(data)).pages))
        email_ok=bool(re.search(r'(?i)[A-Z0-9._%+-]+\s*@\s*[A-Z0-9.-]+\s*\.\s*[A-Z]{2,}',text))
        phone_ok=bool(re.search(r'(?<!\d)(?:\+|00)?[\d() .\-]{8,20}\d(?!\d)',text))
        if len(re.sub(r'\s','',text))<180 or not email_ok or not phone_ok:
            ocr=pdf_ocr(data)
            if ocr: text=(text+'\n'+ocr).strip()
    elif name.endswith('.docx'):
        doc=Document(io.BytesIO(data)); parts=[p.text for p in doc.paragraphs]
        for table in doc.tables:
            for row in table.rows: parts.append(' | '.join(cell.text for cell in row.cells))
        text=clean_text('\n'.join(parts))
    elif name.endswith('.txt'): text=clean_text(data.decode('utf-8',errors='ignore'))
    else: raise ValueError('Use PDF, DOCX or TXT.')
    if len(text)<40: raise ValueError('We could not read enough text from this CV. Please use a clearer PDF/DOCX.')
    return text[:60000]

def ai_json(instructions,prompt):
    if not client: raise RuntimeError('OPENAI_API_KEY is not configured in Railway Variables.')
    r=client.responses.create(model=OPENAI_MODEL,instructions=instructions,input=prompt,text={'format':{'type':'json_object'}},store=False); return json.loads(r.output_text)

def detect_contacts(text):
    # Email: tolerant of OCR-added spaces around @ and dots.
    variants=[text,re.sub(r'\s*([@.])\s*',r'\1',text)]
    emails=[]
    for src in variants: emails += re.findall(r'(?i)(?<![\w.+-])[A-Z0-9._%+-]+\s*@\s*[A-Z0-9.-]+\s*\.\s*[A-Z]{2,}(?![\w.-])',src)
    email=''
    for x in emails:
        x=re.sub(r'\s+','',x).strip('.,;:()[]{}<>')
        if '@' in x and '.' in x.split('@',1)[1]: email=x; break
    lines=text.splitlines(); labeled=[x for x in lines if re.search(r'(?i)\b(phone|mobile|cell|tel|telephone|contact|whatsapp|viber)\b',x)]; sources=labeled+[x for x in lines if x not in labeled]
    patterns=[r'(?<!\d)(?:\+\d{1,3}[\s().-]?)?(?:\d[\s().-]?){8,14}\d(?!\d)',r'(?<!\d)\d{3}[\s.-]\d{3}[\s.-]\d{3,4}(?!\d)']
    for line in sources:
        for pat in patterns:
            for cand in re.findall(pat,line):
                digits=re.sub(r'\D','',cand)
                if not 8<=len(digits)<=15 or len(set(digits))<=2: continue
                if re.search(r'(?i)\b(19|20)\d{2}\s*[-–—]\s*(19|20)\d{2}\b',line): continue
                return email,re.sub(r'\s+',' ',cand).strip(' -.,;:')
    return email,''

def local_profile(cv_text,email,phone):
    lines=[re.sub(r'\s+',' ',x).strip() for x in cv_text.splitlines() if x.strip()]; first=''; last=''
    for line in lines[:20]:
        clean=re.sub(r"[^A-Za-zÀ-ž'’\- ]",'',line).strip(); parts=clean.split()
        if 2<=len(parts)<=4 and all(len(p)>1 for p in parts) and not re.search(r'(?i)cv|resume|curriculum|email|phone|linkedin|profile|experience',clean): first,last=parts[0],parts[-1]; break
    exp=[line[:180] for line in lines if re.search(r'(?i)\b(20\d{2}|19\d{2})\b',line) and (re.search(r'(?i)experience|work|employment|present|current',line) or re.search(r'[-–—]',line))]
    years_found=[int(x) for x in re.findall(r'(?<!\d)(?:19|20)(\d{2})(?!\d)',cv_text)]; years=max(0,min(40,datetime.now().year-min(1900+y if y<30 else 2000+y for y in years_found))) if years_found else 0
    titles=[line for line in lines if re.search(r'(?i)\b(manager|analyst|specialist|engineer|developer|consultant|agent|support|assistant|coordinator|administrator|technician|designer|sales|customer service)\b',line) and len(line)<100]
    return {'first_name':first,'last_name':last,'email':email,'phone':phone,'location':'','job_titles':list(dict.fromkeys(titles))[:8],'years_experience':years,'skills':[],'languages':[],'education':[],'work_experience':exp[:8],'missing_required':[],'profile_ready':False}

def parse_profile(cv_text):
    email,phone=detect_contacts(cv_text); p=local_profile(cv_text,email,phone); missing=[]
    if not p['email']: missing.append('email')
    if not p['phone']: missing.append('phone')
    if not p['first_name']: missing.append('first_name')
    if not p['last_name']: missing.append('last_name')
    if not p['work_experience']: missing.append('work_experience')
    p['missing_required']=missing; p['profile_ready']=not bool(missing); return p

def fetch_json(url):
    req=urllib.request.Request(url,headers={'User-Agent':'JobHunterAI/1.0'})
    with urllib.request.urlopen(req,timeout=8,context=ssl.create_default_context()) as r:return json.loads(r.read().decode('utf-8',errors='ignore'))

def discover_jobs(location,remote,titles):
    jobs=[]
    try:
        data=fetch_json('https://www.arbeitnow.com/api/job-board-api')
        for j in data.get('data',[]):
            hay=' '.join([j.get('title',''),j.get('description',''),j.get('company_name',''),j.get('location','')]).lower()
            if titles and not any(t.lower() in hay for t in titles):continue
            if location and not remote and location.lower() not in hay:continue
            jobs.append({'title':j.get('title',''),'company':j.get('company_name',''),'location':j.get('location',''),'url':j.get('url',''),'source':'Arbeitnow'})
    except Exception as e:app.logger.warning('Arbeitnow search failed: %s',e)
    if remote:
        try:
            data=fetch_json('https://remotive.com/api/remote-jobs')
            for j in data.get('jobs',[]):
                hay=' '.join([j.get('title',''),j.get('description',''),j.get('company_name',''),j.get('candidate_required_location','')]).lower()
                if titles and not any(t.lower() in hay for t in titles):continue
                if location and location.lower() not in hay and location.lower() not in ('worldwide',''):continue
                jobs.append({'title':j.get('title',''),'company':j.get('company_name',''),'location':j.get('candidate_required_location','Remote'),'url':j.get('url',''),'source':'Remotive'})
        except Exception as e:app.logger.warning('Remotive search failed: %s',e)
    seen=set();out=[]
    for j in jobs:
        k=(j['title'].lower(),j['company'].lower(),j['url'])
        if k not in seen:seen.add(k);out.append(j)
    return out[:24]

def match_jobs(profile,jobs):
    if not jobs:return []
    compact=[{'index':i,'title':j.get('title',''),'company':j.get('company',''),'location':j.get('location',''),'source':j.get('source','')} for i,j in enumerate(jobs)]
    result=ai_json('You are a conservative recruitment matching engine. Never invent qualifications. Keep each reason under 16 words.',f'Candidate profile:\n{json.dumps(profile)}\n\nJobs:\n{json.dumps(compact)}\n\nReturn JSON exactly: {{"matches":[{{"index":0,"score":0,"reason":"short truthful reason"}}]}}. Score 0-100.')
    matches={int(x.get('index')):x for x in result.get('matches',[]) if str(x.get('index','')).isdigit()};out=[]
    for i,j in enumerate(jobs):
        m=matches.get(i,{})
        try:score=max(0,min(100,int(m.get('score',0))))
        except Exception:score=0
        out.append({'job':j,'score':score,'reason':str(m.get('reason',''))[:240]})
    return out

def application_draft(profile,job):return ai_json('You write concise professional job applications using only supported facts.',f'Create a short truthful application email. Candidate: {json.dumps(profile)} Job: {json.dumps(job)} Do not invent facts. Return JSON: {{"subject":"","body":""}}')

@app.get('/')
def home():return render_template('index.html')
@app.after_request
def inject_frontend_enhancements(response):
    if response.content_type and 'text/html' in response.content_type and response.status_code==200:
        body=response.get_data(as_text=True);tags='<script src="/static/enhancements.js"></script><script src="/static/api-fix.js"></script><script src="/static/loading.js"></script>'
        if '/static/api-fix.js' not in body:body=body.replace('</body>',tags+'</body>')
        elif '/static/loading.js' not in body:body=body.replace('</body>','<script src="/static/loading.js"></script></body>')
        response.set_data(body)
    return response
@app.get('/health')
def health():return jsonify(status='ok',service='jobhunter-ai')
@app.post('/api/profile')
def profile():
    try:
        p=parse_profile(extract_cv(request.files.get('cv')));pid=secrets.token_urlsafe(16);c=db();c.execute('INSERT INTO profiles VALUES (?,?,?)',(pid,json.dumps(p),datetime.now(timezone.utc).isoformat()));c.commit();c.close();session['profile_id']=pid;return jsonify({'profile_id':pid,**p})
    except Exception as e:app.logger.exception('profile scan failed');return jsonify(error=str(e)),400
@app.post('/api/search')
def search():
    try:
        pid=session.get('profile_id');c=db();row=c.execute('SELECT profile_json FROM profiles WHERE id=?',(pid,)).fetchone() if pid else None
        if not row:c.close();return jsonify(error='Upload your CV first.'),400
        p=json.loads(row['profile_json']);location=request.form.get('location','').strip();remote=request.form.get('remote')=='true';jobs=discover_jobs(location,remote,p.get('job_titles',[]))
        if not jobs:c.close();return jsonify(opportunities=[],count=0,message='No matching public listings were found. Try another country or enable remote jobs.')
        try:matches=match_jobs(p,jobs)
        except Exception as e:app.logger.warning('AI job matching unavailable: %s',e);matches=[{'job':j,'score':0,'reason':'Match score unavailable; review the job details.'} for j in jobs]
        out=[]
        for item in matches:
            j=item['job'];oid=secrets.token_urlsafe(16);c.execute('INSERT INTO opportunities VALUES (?,?,?,?,?,?,?,?,?,?)',(oid,pid,j['title'],j['company'],j['location'],j['url'],j['source'],item['score'],item['reason'],datetime.now(timezone.utc).isoformat()));out.append({'id':oid,**j,'score':item['score'],'reason':item['reason']})
        c.commit();c.close();out.sort(key=lambda x:x['score'],reverse=True);return jsonify(opportunities=out[:20],count=len(out))
    except Exception as e:app.logger.exception('job search failed');return jsonify(error=str(e)),500
@app.post('/api/draft')
def draft():
    try:
        pid=session.get('profile_id');oid=request.form.get('opportunity_id');c=db();r=c.execute('SELECT * FROM opportunities WHERE id=? AND profile_id=?',(oid,pid)).fetchone();p=c.execute('SELECT profile_json FROM profiles WHERE id=?',(pid,)).fetchone();c.close()
        if not r or not p:return jsonify(error='Opportunity not found.'),404
        return jsonify(**application_draft(json.loads(p['profile_json']),dict(r)))
    except Exception as e:return jsonify(error=str(e)),400
@app.post('/api/chat')
def chat():
    try:
        payload=request.get_json(silent=True) or {};message=(payload.get('message') or request.form.get('message','')).strip()
        if not message:return jsonify(error='Please type a question.'),400
        if len(message)>1500:return jsonify(error='Question is too long.'),400
        profile='';pid=session.get('profile_id');c=db()
        if pid:
            row=c.execute('SELECT profile_json FROM profiles WHERE id=?',(pid,)).fetchone()
            if row:profile=json.loads(row['profile_json'])
        c.close();answer=ai_json('You are JobHunter AI, a concise and practical job-search assistant. Answers MUST be short and direct. Default to 1-4 short sentences or up to 4 bullets. Aim for under 60 words.',f'Candidate profile if available: {json.dumps(profile)} User question: {message} Return JSON: {{"answer":"short direct answer; maximum 60 words"}}');text=str(answer.get('answer','')).strip();text=text if len(text)<=700 else text[:697].rsplit(' ',1)[0]+'...';return jsonify(answer=text)
    except Exception as e:app.logger.exception('chat failed');return jsonify(error=str(e)),500
@app.post('/api/feedback')
def feedback():
    try:
        name=request.form.get('name','').strip()[:80];message=request.form.get('message','').strip()[:1000];rating=max(1,min(5,int(request.form.get('rating','5'))))
        if not message:return jsonify(error='Please write a short message.'),400
        c=db();c.execute('INSERT INTO feedback VALUES (?,?,?,?,?)',(secrets.token_urlsafe(12),name,rating,message,datetime.now(timezone.utc).isoformat()));c.commit();c.close();return jsonify(ok=True)
    except Exception as e:return jsonify(error=str(e)),400
@app.errorhandler(404)
def not_found(e):
    if request.path.startswith('/api/'):return jsonify(error='Not found'),404
    return render_template('index.html'),404
@app.errorhandler(413)
def too_large(e):return jsonify(error='CV is too large. Maximum size is 8 MB.'),413
if __name__=='__main__':app.run(host='0.0.0.0',port=int(os.getenv('PORT','5000')))
