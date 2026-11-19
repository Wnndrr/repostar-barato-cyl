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
      if (url.pathname === "/") return json(req, { servicio: "Alerta Chollo · Repostar Barato CyL", ok: true });
      return json(req, { error: "no encontrado" }, 404);
    } catch (e) {
      return json(req, { error: "petición no válida" }, 400);
    }
  },
};
