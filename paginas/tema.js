(()=>{const d=document.documentElement,mq=matchMedia("(prefers-color-scheme: dark)");
const actual=()=>d.dataset.theme||(mq.matches?"dark":"light");
function pintar(){const o=actual()==="dark";document.querySelectorAll(".tema").forEach(b=>{b.textContent=o?"☀️ Modo claro":"🌙 Modo oscuro";b.setAttribute("aria-label",o?"Cambiar a tema claro":"Cambiar a tema oscuro")});
  const m=document.querySelector('meta[name="theme-color"]');if(m)m.content=o?"#0e141a":"#121a22"}
document.addEventListener("click",e=>{const b=e.target.closest(".tema");if(!b)return;const n=actual()==="dark"?"light":"dark";d.dataset.theme=n;try{localStorage.setItem("tema",n)}catch(_){}pintar()});
mq.addEventListener&&mq.addEventListener("change",pintar);
document.readyState==="loading"?document.addEventListener("DOMContentLoaded",pintar):pintar()})();
