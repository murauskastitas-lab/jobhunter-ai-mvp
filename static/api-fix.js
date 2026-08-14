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
    if(!missing.length){box.innerHTML='<div class="ok">✓ Profile complete — ready to hunt!</div>';return;}
    const labels={email:'Email address',phone:'Phone number',first_name:'First name',last_name:'Last name',work_experience:'Work experience'};
    box.innerHTML='<div class="warn"><b>We still need:</b> '+missing.map(x=>labels[x]||x).join(', ')+'</div>'+
      ['email','phone'].filter(x=>missing.includes(x)).map(x=>`<label class="missing-contact-label">${labels[x]}<input id="missing-${x}" class="missing-contact" type="text" placeholder="Enter your ${labels[x].toLowerCase()}"></label>`).join('');
  }
  async function scan(form){
    const btn=form.querySelector('.upload-btn');
    if(btn){btn.disabled=true;btn.dataset.old=btn.textContent;btn.textContent='⏳ AI is reading your CV…';}
    setStatus('⏳ Reading your CV…');
    try{
      const r=await fetch('/api/profile',{method:'POST',body:new FormData(form),headers:{'Accept':'application/json'}});
      const d=await readApi(r);
      $('#profile')?.classList.remove('hidden');
      $('#intro').textContent=d.missing_required?.length?'A few details need your attention before we start hunting.':'🎉 Your profile looks ready. Let’s go hunting!';
      renderMissingFields(d);
      $('#summary').innerHTML=`<b>${esc(d.first_name)} ${esc(d.last_name)}</b><br>${esc(d.email||'')} · ${esc(d.phone||'')}<br>${esc((d.job_titles||[]).join(', '))} · ${esc(d.years_experience||0)} years experience`;
      $('#hunt').disabled=!!d.missing_required?.length;
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
    // If the original app handler is used, at least show visible progress immediately.
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
  style.textContent='.missing-contact-label{display:block;margin:12px 0;font-weight:800;font-size:12px}.missing-contact{display:block;width:100%;box-sizing:border-box;margin-top:6px;padding:11px 12px;border:1px solid #d9d6e8;border-radius:10px;font:inherit}.ai-loading{text-align:center;padding:35px!important}.ai-spinner{width:30px;height:30px;margin:0 auto 12px;border:4px solid #e8e3f8;border-top-color:#7045ee;border-radius:50%;animation:jhspin .8s linear infinite}@keyframes jhspin{to{transform:rotate(360deg)}}#status.error{color:#b42318;font-weight:800}#status.success{color:#087443;font-weight:800}';
  document.head.appendChild(style);
})();
