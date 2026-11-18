// Permite instalar la web como app y verla sin conexión con los últimos precios cargados.
const CACHE = "repostar-v2";
self.addEventListener("install", e => {
  e.waitUntil(caches.open(CACHE).then(c => c.addAll(["/", "/logo-192.png", "/logo-512.png"])).then(() => self.skipWaiting()));
});
self.addEventListener("activate", e => {
  e.waitUntil(caches.keys().then(ks => Promise.all(ks.filter(k => k !== CACHE).map(k => caches.delete(k)))).then(() => self.clients.claim()));
});
self.addEventListener("fetch", e => {
  const r = e.request;
  if (r.method !== "GET" || new URL(r.url).origin !== location.origin) return;
  // Primero la red (precios siempre al día); si no hay conexión, la última copia guardada.
  // Páginas, scripts y datos: preguntar siempre al servidor si hay versión nueva (no usar copias viejas del navegador).
  const fresco = r.mode === "navigate" || /\.(html|js|json|webmanifest|xml|txt)$/.test(new URL(r.url).pathname) || new URL(r.url).pathname.endsWith("/");
  e.respondWith(fetch(fresco ? new Request(r, { cache: "no-cache" }) : r).then(res => {
    if (res.ok) { const copia = res.clone(); caches.open(CACHE).then(c => c.put(r, copia)); }
    return res;
  }).catch(() => caches.match(r).then(m => m || caches.match("/"))));
});
