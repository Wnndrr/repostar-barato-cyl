"""Manda las notificaciones de "Alerta Chollo" cuando baja un precio.

Uso (en GitHub Actions, después de actualizar los precios):
    python scripts/avisos.py <precios_anteriores.json> datos/gasolineras.json
Compara los precios de la actualización anterior con los nuevos y avisa a cada móvil
de las bajadas que le interesan. Necesita VAPID_PRIVATE_KEY y datos/avisos.json.
"""
import hashlib
import json
import math
import os
import sys
import urllib.request
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
PROV = ["Ávila", "Burgos", "León", "Palencia", "Salamanca", "Segovia", "Soria", "Valladolid", "Zamora"]
COMB = {5: "gasolina 95", 6: "diésel", 7: "gasolina 98", 10: "autogás (GLP)", 11: "AdBlue", 12: "gas natural"}
WEB = "https://repostarbaratocyl.es"


def pueblo(m):
    if "(" in m and m.endswith(")"):
        a, b = m[:-1].split("(", 1)
        art = b.strip()
        return (art + (" " if not art.endswith("'") else "") + a.strip()).strip()
    return m


def euros(v, f):
    return f"{v / 1000:.3f}".replace(".", ",") + (" €/kg" if f == 12 else " €")


def km(a, b, c, d):
    r = math.pi / 180
    x = math.sin((c - a) * r / 2) ** 2 + math.cos(a * r) * math.cos(c * r) * math.sin((d - b) * r / 2) ** 2
    return 12742 * math.asin(math.sqrt(x))


def cargar(p):
    d = json.loads(Path(p).read_text(encoding="utf-8"))
    return d["gasolineras"] if isinstance(d, dict) else d


def buscar(lista, a):
    for s in lista:
        if s[8] == a["la"] and s[9] == a["lo"]:
            return s
    mejor, dist = None, 0.3
    for s in lista:
        if s[2] == a["n"]:
            d = km(a["la"], a["lo"], s[8], s[9])
            if d < dist:
                mejor, dist = s, d
    return mejor


def minimo(lista, f, p=None):
    xs = [s for s in lista if s[f] and (p is None or s[0] == p)]
    return min(xs, key=lambda s: s[f]) if xs else None


def bajadas(av, antes, ahora):
    """Devuelve una frase por cada aviso cuyo precio ha bajado."""
    out = []
    for a in av:
        f = a["f"]
        if a["t"] == "gas":
            s0, s1 = buscar(antes, a), buscar(ahora, a)
            if s0 and s1 and s0[f] and s1[f] and s1[f] < s0[f]:
                out.append(f"{s1[2]} ({pueblo(s1[1])}): {COMB[f]} a {euros(s1[f], f)}, {(s0[f] - s1[f]) / 10:.1f} cts menos".replace(".", ","))
        else:
            p = a.get("p") if a["t"] == "prov" else None
            zona = PROV[p] if p is not None else "Castilla y León"
            m0, m1 = minimo(antes, f, p), minimo(ahora, f, p)
            if m0 and m1 and m1[f] < m0[f]:
                out.append(f"La {COMB[f]} más barata de {zona} baja a {euros(m1[f], f)} en {m1[2]} ({pueblo(m1[1])})")
    return out


def peticion(url, admin, datos=None, intentos=4):
    import time
    for n in range(intentos):
        try:
            return _peticion(url, admin, datos)
        except Exception as e:  # red o certificado todavía no listos: reintentar
            if n == intentos - 1:
                raise
            print("No se pudo conectar con el servidor de avisos, reintentando…", str(e)[:120])
            time.sleep(15)


def _peticion(url, admin, datos=None):
    req = urllib.request.Request(url, data=json.dumps(datos).encode() if datos is not None else None,
                                 method="POST" if datos is not None else "GET")
    req.add_header("Authorization", "Bearer " + admin)
    req.add_header("User-Agent", "RepostarBaratoCyL-AlertaChollo/1.0 (+https://repostarbaratocyl.es)")
    req.add_header("Content-Type", "application/json")
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.loads(r.read())


def prueba():
    """Manda una notificación de prueba a todos los móviles apuntados (para comprobar que llegan)."""
    from pywebpush import webpush, WebPushException
    clave = os.environ["VAPID_PRIVATE_KEY"].strip()
    servidor = json.loads((RAIZ / "datos" / "avisos.json").read_text(encoding="utf-8"))["url"]
    cfg = json.loads((RAIZ / "scripts" / "avisos_config.json").read_text(encoding="utf-8"))
    admin = hashlib.sha256(("repostar-avisos:" + clave).encode()).hexdigest()
    subs = peticion(servidor + "/admin/lista", admin)
    ok = 0
    for s in subs:
        try:
            webpush(subscription_info=s["sub"],
                    data=json.dumps({"title": "🔔 Alerta Chollo funciona", "body": "Este es un aviso de prueba. Te avisaremos cuando baje el precio que sigues.", "url": WEB + "/avisos/"}),
                    vapid_private_key=clave, vapid_claims={"sub": cfg["contacto"]}, ttl=3600)
            ok += 1
        except WebPushException as e:
            print("No se pudo avisar a un móvil:", getattr(e.response, "status_code", None), str(e)[:200])
    print(f"Prueba de Alerta Chollo: {ok} de {len(subs)} móviles avisados.")
    return 0


def main():
    if len(sys.argv) > 1 and sys.argv[1] == "--prueba":
        return prueba()
    if len(sys.argv) < 3 or not Path(sys.argv[1]).exists():
        print("No hay precios anteriores con los que comparar: no se mandan avisos.")
        return 0
    clave = os.environ.get("VAPID_PRIVATE_KEY", "").strip()
    cfg_srv = RAIZ / "datos" / "avisos.json"
    if not clave or not cfg_srv.exists():
        print("Alerta Chollo todavía no está configurada (falta la clave o el servidor): no se mandan avisos.")
        return 0
    servidor = json.loads(cfg_srv.read_text(encoding="utf-8"))["url"]
    cfg = json.loads((RAIZ / "scripts" / "avisos_config.json").read_text(encoding="utf-8"))
    admin = hashlib.sha256(("repostar-avisos:" + clave).encode()).hexdigest()

    antes, ahora = cargar(sys.argv[1]), cargar(sys.argv[2])
    subs = peticion(servidor + "/admin/lista", admin)
    print(f"Alerta Chollo: conectado con el servidor, {len(subs)} móviles con avisos.")
    if antes == ahora or not subs:
        print("No hay bajadas que comprobar ahora: no se mandan avisos.")
        return 0

    from pywebpush import webpush, WebPushException

    enviados, borrar = 0, []
    for s in subs:
        frases = bajadas(s.get("avisos", []), antes, ahora)
        if not frases:
            continue
        titulo = "¡Baja el precio!" if len(frases) == 1 else f"¡Bajan {len(frases)} precios que sigues!"
        cuerpo = "\n".join(frases[:4]) + ("\n…y más en la web" if len(frases) > 4 else "")
        try:
            webpush(subscription_info=s["sub"],
                    data=json.dumps({"title": titulo, "body": cuerpo, "url": WEB + "/avisos/"}),
                    vapid_private_key=clave, vapid_claims={"sub": cfg["contacto"]}, ttl=43200)
            enviados += 1
        except WebPushException as e:
            code = getattr(e.response, "status_code", None)
            if code in (404, 410):
                borrar.append(s["k"])
            else:
                print("Error al avisar a un móvil:", code, str(e)[:200])
    if borrar:
        peticion(servidor + "/admin/borrar", admin, {"claves": borrar})
    print(f"Alerta Chollo: {len(subs)} móviles con avisos, {enviados} notificaciones enviadas, {len(borrar)} bajas automáticas.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
