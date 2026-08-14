(()=>{
  const $=s=>document.querySelector(s);
  async function readApi(response){
    const text=await response.text();
    let data=null;
    try{data=JSON.parse(text)}catch(_){
      const snippet=text.replace(/\s+/g,' ').slice(0,180);
      throw new Error(`Server returned HTML instead of JSON (${response.status}). ${snippet}`);
    }
    if(!response.ok) throw new Error(data?.error||`Request failed (${response.status})`);
    return data;
  }
  function setStatus(msg,kind=''){
    const el=$('#status');
    if(el){el.textContent=msg;el.className=kind;}
  }
  function renderMissingFields(data){
    const box=$('#missing');
    if(!box)return;
    const missing=data.missing_required||[];
    // Never ask the user to re-type contact details that should have been read from the CV.
    // Missing contact fields are reported as a scan warning, but they do not block the job search.
    const contacts=missing.filter(x=>x==='email'||x==='phone');
    const other=missing.filter(x=>!['email','phone'].includes(x));
    if(!missing.length){
      box.innerHTML='<div class="ok">✓ Profile complete — ready to hunt!</div>';
      return;
    }
    const labels={email:'email address',phone:'phone number',first_name:'first name',last_name:'last name',work_experience:'work experience'};
    const parts=[];
    if(contacts.length) parts.push(`<div class="scan-note">⚠️ I could not reliably read ${contacts.map(x=>labels[x]).join(' and ')} from the document text. <b>Your job search can continue without re-entering them.</b></div>`);
    if(other.length) parts.push(`<div class="warn"><b>Profile needs review:</b> ${other.map(x=>labels[x]||x).join(', ')}</div>`);
    box.innerHTML=parts.join('');
  }
  async function scan(form){
    const btn=form.querySelector('.upload-btn');
    if(btn){btn.disabled=true;btn.dataset.old=btn.textContent;btn.textContent='⏳ Reading your CV…';}
    setStatus('⏳ Reading your CV…');
    try{
      const r=await fetch('/api/profile',{method:'POST',body:new FormData(form),headers:{'Accept':'application/json'}});
      const d=await readApi(r);
      $('#profile')?.classList.remove('hidden');
      $('#intro').textContent='🎉 Your CV has been scanned. Review the profile, choose your target and let JobHunter hunt.';
      renderMissingFields(d);
      $('#summary').innerHTML=`<b>${esc(d.first_name)} ${esc(d.last_name)}</b><br>${esc(d.email||'Contact not detected automatically')} · ${esc(d.phone||'Contact not detected automatically')}<br>${esc((d.job_titles||[]).join(', '))} · ${esc(d.years_experience||0)} years experience`;
      // Contact detection must never block the core product flow.
      $('#hunt').disabled=false;
      $('#profile').scrollIntoView({behavior:'smooth'});
      setStatus('✓ CV analyzed successfully','success');
    }catch(e){
      setStatus('❌ '+e.message,'error');
      alert(e.message);
    }finally{
      if(btn){btn.disabled=false;btn.textContent=btn.dataset.old||'✨ Scan my CV with AI';}
    }
  }
  document.addEventListener('submit',e=>{
    if(e.target?.id!=='cvForm')return;
    e.preventDefault();e.stopImmediatePropagation();scan(e.target);
  },true);
  document.addEventListener('click',e=>{
    const hunt=e.target?.closest?.('#hunt');
    if(!hunt)return;
    hunt.dataset.busy='1';
    hunt.textContent='⏳ Searching jobs…';
    const results=$('#results');
    if(results){
      results.classList.remove('hidden');
      const jobs=$('#jobs');
      if(jobs)jobs.innerHTML='<div class="card ai-loading"><div class="ai-spinner"></div><h3>🔎 AI is hunting for you…</h3><p>Scanning public listings and comparing them with your profile.</p></div>';
      $('#count').textContent='Searching…';
    }
  },true);
  const style=document.createElement('style');
  style.textContent='.scan-note{margin:10px 0;padding:12px 14px;border-radius:12px;background:#fff8e6;border:1px solid #f0d78a;color:#795b00;line-height:1.45;font-size:12px}.ai-loading{text-align:center;padding:35px!important}.ai-spinner{width:30px;height:30px;margin:0 auto 12px;border:4px solid #e8e3f8;border-top-color:#7045ee;border-radius:50%;animation:jhspin .8s linear infinite}@keyframes jhspin{to{transform:rotate(360deg)}}#status.error{color:#b42318;font-weight:800}#status.success{color:#087443;font-weight:800}';
  document.head.appendChild(style);
})();
