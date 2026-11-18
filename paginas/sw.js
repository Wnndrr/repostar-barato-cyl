// Permite instalar la web como app y verla sin conexión con los últimos precios cargados.
const CACHE = "repostar-v3";
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

// Alerta Chollo: mostrar la notificación de bajada de precio y abrir la web al tocarla.
self.addEventListener("push", e => {
  let d = {};
  try { d = e.data ? e.data.json() : {}; } catch (_) { d = { body: e.data ? e.data.text() : "" }; }
  e.waitUntil(self.registration.showNotification(d.title || "Alerta Chollo", {
    body: d.body || "Ha bajado un precio que sigues.", icon: "/logo-192.png", badge: "/logo-192.png",
    tag: "alerta-chollo", renotify: true, data: { url: d.url || "/avisos/" }
  }));
});
self.addEventListener("notificationclick", e => {
  e.notification.close();
  const url = (e.notification.data && e.notification.data.url) || "/";
  e.waitUntil(clients.matchAll({ type: "window", includeUncontrolled: true }).then(cs => {
    for (const c of cs) { if ("focus" in c) { c.navigate && c.navigate(url); return c.focus(); } }
    return clients.openWindow(url);
  }));
});
