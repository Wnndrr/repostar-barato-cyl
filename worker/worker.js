// Servidor de "Alerta Chollo": guarda qué avisos quiere cada móvil.
// No guarda nombres, correos ni ubicaciones: solo la dirección de notificación del navegador y los avisos elegidos.
const ORIGENES = ["https://repostarbaratocyl.es", "https://www.repostarbaratocyl.es"];
const MAX_AVISOS = 30;

function cors(req) {
  const o = req.headers.get("Origin") || "";
  return {
    "Access-Control-Allow-Origin": ORIGENES.includes(o) ? o : ORIGENES[0],
    "Access-Control-Allow-Methods": "POST, GET, OPTIONS",
    "Access-Control-Allow-Headers": "Content-Type, Authorization",
    "Access-Control-Max-Age": "86400",
    "Vary": "Origin",
  };
}
const json = (req, data, status = 200) =>
  new Response(JSON.stringify(data), { status, headers: { "Content-Type": "application/json", ...cors(req) } });

async function clave(endpoint) {
  const h = await crypto.subtle.digest("SHA-256", new TextEncoder().encode(endpoint));
  return "s:" + [...new Uint8Array(h)].map(b => b.toString(16).padStart(2, "0")).join("");
}

function avisosValidos(a) {
  if (!Array.isArray(a) || a.length > MAX_AVISOS) return null;
  const out = [];
  for (const x of a) {
    if (!x || ![5, 6, 7, 10, 11, 12].includes(x.f)) return null;
    const d = ["b", "s", "a"].includes(x.d) ? x.d : "b"; // b = baja, s = sube, a = ambas
    if (x.t === "cyl") out.push({ f: x.f, t: "cyl", d });
    else if (x.t === "prov" && Number.isInteger(x.p) && x.p >= 0 && x.p <= 8) out.push({ f: x.f, t: "prov", p: x.p, d });
    else if (x.t === "gas" && typeof x.la === "number" && typeof x.lo === "number" && typeof x.n === "string")
      out.push({ f: x.f, t: "gas", la: x.la, lo: x.lo, n: x.n.slice(0, 80), d });
    else return null;
  }
  return out;
}

// ---- ¿Dónde quiero ir?: rutas y búsqueda de lugares con openrouteservice (la clave vive solo aquí) ----
const ORS = "https://api.heigit.org";
function simplificar(c, max = 400) {
  if (c.length <= max) return c;
  const paso = Math.ceil(c.length / max), out = [];
  for (let i = 0; i < c.length; i += paso) out.push(c[i]);
  out.push(c[c.length - 1]);
  return out;
}
async function rutas(req, env, url) {
  if (!env.ORS) return json(req, { error: "sin_clave" }, 503);
  const cache = caches.default;
  const clave = new Request(url.toString(), { method: "GET" });
  const hit = await cache.match(clave);
  if (hit) { const r = new Response(hit.body, hit); for (const [k, v] of Object.entries(cors(req))) r.headers.set(k, v); return r; }
  let datos, ttl;
  if (url.pathname === "/lugar") {
    const q = (url.searchParams.get("q") || "").trim().slice(0, 80);
    if (q.length < 3) return json(req, []);
    const r = await fetch(`${ORS}/pelias/v1/autocomplete?text=${encodeURIComponent(q)}&boundary.country=ES&size=6&lang=es`, { headers: { Authorization: env.ORS } });
    if (!r.ok) return json(req, { error: "servicio", status: r.status }, 502);
    const g = await r.json();
    datos = (g.features || []).map(f => ({ n: f.properties.label, lon: +f.geometry.coordinates[0].toFixed(5), lat: +f.geometry.coordinates[1].toFixed(5) }));
    ttl = 604800;
  } else {
    const num = v => { const x = (v || "").split(",").map(Number); return x.length === 2 && x.every(Number.isFinite) ? x.map(n => +n.toFixed(4)) : null; };
    const o = num(url.searchParams.get("o")), d = num(url.searchParams.get("d"));
    if (!o || !d) return json(req, { error: "coordenadas" }, 400);
    const pedir = async evitar => {
      const body = { coordinates: [o, d], instructions: false, extra_info: ["tollways"] };
      if (evitar) body.options = { avoid_features: ["tollways"] };
      const r = await fetch(`${ORS}/openrouteservice/v2/directions/driving-car/geojson`, {
        method: "POST", headers: { Authorization: env.ORS, "Content-Type": "application/json", Accept: "application/geo+json" }, body: JSON.stringify(body) });
      if (!r.ok) return { error: r.status };
      const g = await r.json(), f = g.features && g.features[0];
      if (!f) return { error: "vacía" };
      const tw = (((f.properties.extras || {}).tollways || {}).summary || []).filter(x => x.value > 0).reduce((a, x) => a + x.distance, 0);
      return { km: f.properties.summary.distance / 1000, min: f.properties.summary.duration / 60, peajeKm: tw / 1000,
               c: simplificar(f.geometry.coordinates).map(([x, y]) => [+y.toFixed(5), +x.toFixed(5)]) };
    };
    const [con, sin] = await Promise.all([pedir(false), pedir(true)]);
    if (con.error && sin.error) return json(req, { error: "servicio", status: con.error }, 502);
    datos = { con: con.error ? null : con, sin: sin.error ? null : sin };
    ttl = 86400;
  }
  const resp = new Response(JSON.stringify(datos), { headers: { "Content-Type": "application/json", "Cache-Control": `public, max-age=${ttl}` } });
  await cache.put(clave, resp.clone());
  const r = new Response(resp.body, resp); for (const [k, v] of Object.entries(cors(req))) r.headers.set(k, v); return r;
}

export default {
  async fetch(req, env) {
    const url = new URL(req.url);
    if (req.method === "OPTIONS") return new Response(null, { status: 204, headers: cors(req) });
    const admin = req.headers.get("Authorization") === "Bearer " + env.ADMIN;

    try {
      if (req.method === "POST" && url.pathname === "/alta") {
        if (Number(req.headers.get("Content-Length") || 0) > 20000) return json(req, { error: "demasiado grande" }, 413);
        const b = await req.json();
        const s = b && b.sub;
        if (!s || typeof s.endpoint !== "string" || !s.endpoint.startsWith("https://") || !s.keys || !s.keys.p256dh || !s.keys.auth)
          return json(req, { error: "suscripción no válida" }, 400);
        const avisos = avisosValidos(b.avisos);
        if (!avisos) return json(req, { error: "avisos no válidos" }, 400);
        const k = await clave(s.endpoint);
        if (!avisos.length) { await env.KV.delete(k); return json(req, { ok: true, avisos: 0 }); }
        await env.KV.put(k, JSON.stringify({ sub: { endpoint: s.endpoint, keys: { p256dh: s.keys.p256dh, auth: s.keys.auth } }, avisos, t: Date.now() }));
        return json(req, { ok: true, avisos: avisos.length });
      }
      if (req.method === "POST" && url.pathname === "/baja") {
        const b = await req.json();
        if (b && typeof b.endpoint === "string") await env.KV.delete(await clave(b.endpoint));
        return json(req, { ok: true });
      }
      if (req.method === "GET" && url.pathname === "/admin/lista") {
        if (!admin) return json(req, { error: "no autorizado" }, 401);
        const todas = []; let cursor;
        do {
          const r = await env.KV.list({ prefix: "s:", cursor });
          for (const k of r.keys) { const v = await env.KV.get(k.name); if (v) todas.push({ k: k.name, ...JSON.parse(v) }); }
          cursor = r.list_complete ? null : r.cursor;
        } while (cursor);
        return json(req, todas);
      }
      if (req.method === "POST" && url.pathname === "/admin/borrar") {
        if (!admin) return json(req, { error: "no autorizado" }, 401);
        const b = await req.json();
        for (const k of (b.claves || []).slice(0, 500)) if (typeof k === "string" && k.startsWith("s:")) await env.KV.delete(k);
        return json(req, { ok: true });
      }
      if (req.method === "GET" && (url.pathname === "/ruta" || url.pathname === "/lugar")) return await rutas(req, env, url);
      if (url.pathname === "/") return json(req, { servicio: "Alerta Chollo · Repostar Barato CyL", ok: true });
      return json(req, { error: "no encontrado" }, 404);
    } catch (e) {
      return json(req, { error: "petición no válida" }, 400);
    }
  },
};
