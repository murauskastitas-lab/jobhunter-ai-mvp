(()=>{
const style=document.createElement('style');
style.textContent=`
.jh-loading-overlay{position:fixed;inset:0;background:rgba(248,247,255,.78);backdrop-filter:blur(7px);display:flex;align-items:center;justify-content:center;z-index:9999;opacity:0;pointer-events:none;transition:opacity .2s ease}
.jh-loading-overlay.show{opacity:1;pointer-events:auto}
.jh-loading-card{width:min(420px,calc(100vw - 36px));background:#fff;border:1px solid #e7e2f4;border-radius:28px;padding:32px 28px;text-align:center;box-shadow:0 30px 90px rgba(65,48,130,.22)}
.jh-loader{width:66px;height:66px;margin:0 auto 18px;border:6px solid #eee9ff;border-top-color:#7045ee;border-right-color:#ef2a9f;border-radius:50%;animation:jhSpin .85s linear infinite}
.jh-loading-card h3{margin:0 0 7px;font:900 22px Nunito,sans-serif;color:#252746}
.jh-loading-card p{margin:0;color:#777b91;font:600 13px Nunito,sans-serif}
.jh-loading-dots{display:inline-flex;gap:5px;margin-top:14px}.jh-loading-dots i{width:7px;height:7px;border-radius:50%;background:#7045ee;animation:jhDot 1.1s infinite}.jh-loading-dots i:nth-child(2){animation-delay:.15s}.jh-loading-dots i:nth-child(3){animation-delay:.3s}
.upload-btn.jh-loading{position:relative;color:transparent!important;pointer-events:none}.upload-btn.jh-loading:after{content:'AI is scanning…';position:absolute;inset:0;display:flex;align-items:center;justify-content:center;color:#fff;font-weight:900}
@keyframes jhSpin{to{transform:rotate(360deg)}}@keyframes jhDot{0%,70%,100%{transform:translateY(0);opacity:.35}35%{transform:translateY(-5px);opacity:1}}
`;
document.head.appendChild(style);
const overlay=document.createElement('div');overlay.className='jh-loading-overlay';overlay.innerHTML=`<div class="jh-loading-card"><div class="jh-loader"></div><h3>🤖 AI is reading your CV</h3><p>Checking your contact details, experience and skills…</p><div class="jh-loading-dots"><i></i><i></i><i></i></div></div>`;document.body.appendChild(overlay);
const form=()=>document.querySelector('#cvForm');
function show(){overlay.classList.add('show');document.querySelector('.upload-btn')?.classList.add('jh-loading');}
function hide(){overlay.classList.remove('show');document.querySelector('.upload-btn')?.classList.remove('jh-loading');}
const originalFetch=window.fetch;
window.fetch=async function(...args){
 const url=String(args[0]?.url||args[0]||'');
 const isProfile=url.includes('/api/profile');
 if(isProfile)show();
 try{return await originalFetch.apply(this,args)}finally{if(isProfile)hide();}
};
function bind(){const f=form();if(!f||f.dataset.jhLoadingBound)return;if(!f.querySelector('#cvFile'))return;f.dataset.jhLoadingBound='1';f.addEventListener('submit',()=>{if(f.checkValidity())show();});}
if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',bind);else bind();
new MutationObserver(bind).observe(document.documentElement,{childList:true,subtree:true});
})();
