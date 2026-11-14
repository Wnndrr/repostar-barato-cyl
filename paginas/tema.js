(()=>{const d=document.documentElement,mq=matchMedia("(prefers-color-scheme: dark)");
const elegido=()=>{try{return localStorage.getItem("tema")||"auto"}catch(_){return"auto"}};
const actual=()=>d.dataset.theme||(mq.matches?"dark":"light");
function aplicar(t){if(t==="auto"){delete d.dataset.theme;try{localStorage.removeItem("tema")}catch(_){}}else{d.dataset.theme=t;try{localStorage.setItem("tema",t)}catch(_){}}
  const m=document.querySelector('meta[name="theme-color"]');if(m)m.content=actual()==="dark"?"#0e141a":"#121a22";pintar()}
const st=document.createElement("style");st.textContent=`
.opcmenu{position:fixed;z-index:3000;min-width:240px;background:var(--surface,#fff);color:var(--fg,#17212b);border:1px solid var(--line,#d9dfe5);border-radius:14px;box-shadow:0 10px 30px rgba(0,0,0,.25);padding:8px;font:15px var(--f-body,system-ui)}
.opcmenu h4{margin:6px 10px 4px;font-size:12px;letter-spacing:.08em;text-transform:uppercase;color:var(--muted,#5b6876)}
.opcmenu button{display:flex;width:100%;align-items:center;gap:10px;border:0;background:transparent;color:inherit;font:inherit;text-align:left;padding:10px 12px;border-radius:10px;cursor:pointer}
.opcmenu button:hover,.opcmenu button:focus-visible{background:var(--accent-soft,#e3eefa)}
.opcmenu button[aria-checked="true"]::after{content:"✓";margin-left:auto;color:var(--accent,#0b5cad);font-weight:700}
.opcmenu hr{border:0;border-top:1px solid var(--line,#d9dfe5);margin:6px 4px}
.opc{background:transparent;border:1px solid var(--line);color:inherit;border-radius:999px;padding:4px 12px;font:600 14px var(--f-body,system-ui);cursor:pointer;white-space:nowrap}
.opc:hover,.opc[aria-expanded="true"]{border-color:var(--accent);color:var(--accent)}`;document.head.appendChild(st);
const menu=document.createElement("div");menu.className="opcmenu";menu.hidden=true;menu.setAttribute("role","menu");
menu.innerHTML=`<h4>Tema</h4><button role="menuitemradio" data-t="light">☀️ Tema claro</button><button role="menuitemradio" data-t="dark">🌙 Tema oscuro</button><button role="menuitemradio" data-t="auto">🌗 Automático (como el móvil)</button><hr><h4>Widget</h4><button role="menuitem" data-w="1">⭐ Widget: mi gasolinera</button>`;
document.addEventListener("DOMContentLoaded",()=>document.body.appendChild(menu));if(document.body)document.body.appendChild(menu);
function pintar(){const e=elegido();menu.querySelectorAll("[data-t]").forEach(b=>b.setAttribute("aria-checked",b.dataset.t===e))}
let btnAbierto=null,y0=0;
function abrir(b){const r=b.getBoundingClientRect();menu.hidden=false;const w=menu.offsetWidth;menu.style.top=(r.bottom+8)+"px";menu.style.left=Math.max(8,Math.min(innerWidth-w-8,r.right-w))+"px";b.setAttribute("aria-expanded","true");btnAbierto=b;y0=scrollY;pintar();menu.querySelector("button").focus({preventScroll:true})}
function cerrar(){if(menu.hidden)return;menu.hidden=true;if(btnAbierto){btnAbierto.setAttribute("aria-expanded","false");btnAbierto=null}}
document.addEventListener("click",e=>{const b=e.target.closest(".opc");if(b){menu.hidden?abrir(b):cerrar();return}
  const t=e.target.closest(".opcmenu [data-t]");if(t){aplicar(t.dataset.t);cerrar();return}
  if(e.target.closest(".opcmenu [data-w]")){cerrar();if(window.abrirWidget)window.abrirWidget();else location.href="/?widget=1#migasolinera";return}
  if(!e.target.closest(".opcmenu"))cerrar()});
document.addEventListener("keydown",e=>{if(e.key==="Escape")cerrar()});
addEventListener("scroll",()=>{if(Math.abs(scrollY-y0)>40)cerrar()},{passive:true});addEventListener("resize",cerrar);
mq.addEventListener&&mq.addEventListener("change",()=>aplicar(elegido()));
})();
