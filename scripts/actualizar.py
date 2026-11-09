"""Descarga los precios de las gasolineras de Castilla y León y genera la web.

Uso:  python scripts/actualizar.py
Crea la carpeta  sitio/  con la web lista para publicar.
Solo usa la biblioteca estándar de Python (no hay que instalar nada).
"""
import json
import os
import ssl
import re
import shutil
import sys
import time
import urllib.request
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
DATOS = RAIZ / "datos"
SALIDA = RAIZ / "sitio"

# Dirección pública de la web. Cuando tengas dominio propio, cámbiala aquí
# (o define la variable de entorno URL_WEB en GitHub).
URL_WEB = os.environ.get("URL_WEB") or "https://repostarbaratocyl.es".rstrip("/")

API_MINISTERIO = (
    "https://sedeaplicaciones.minetur.gob.es/ServiciosRESTCarburantes/"
    "PreciosCarburantes/EstacionesTerrestres/FiltroCCAA/08"  # 08 = Castilla y León
)
API_JUNTA_CARGA = (
    "https://analisis.datosabiertos.jcyl.es/api/explore/v2.1/catalog/datasets/"
    "puntos-de-recarga-del-vehiculo-electrico/records?limit=100&offset={}"
)

# Orden de provincias usado en la web (código INE -> índice)
PROVINCIAS = {"05": 0, "09": 1, "24": 2, "34": 3, "37": 4, "40": 5, "42": 6, "47": 7, "49": 8}
MESES = ["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio",
         "agosto", "septiembre", "octubre", "noviembre", "diciembre"]


def contexto_ssl():
    # El servidor del Ministerio usa una configuración TLS antigua que Python moderno rechaza.
    ctx = ssl.create_default_context()
    ctx.options |= getattr(ssl, "OP_LEGACY_SERVER_CONNECT", 0x4)
    try:
        ctx.set_ciphers("DEFAULT:@SECLEVEL=1")
    except ssl.SSLError:
        pass
    ctx.minimum_version = ssl.TLSVersion.TLSv1_2
    return ctx


def descargar_json(url, intentos=4):
    ultimo = None
    for n in range(intentos):
        try:
            req = urllib.request.Request(url, headers={
                "Accept": "application/json",
                "User-Agent": "RepostarBaratoCyL/1.0 (web de precios de carburantes)",
            })
            with urllib.request.urlopen(req, timeout=90, context=contexto_ssl()) as r:
                return json.loads(r.read().decode("utf-8"))
        except Exception as e:  # noqa: BLE001
            ultimo = e
            print(f"  Intento {n + 1} fallido: {e}", file=sys.stderr)
            time.sleep(10 * (n + 1))
    raise RuntimeError(f"No se pudo descargar {url}: {ultimo}")


PEQUENAS = {"de", "del", "la", "las", "los", "y", "en", "a", "el", "al"}


def bonito(texto, marca=False):
    """Pasa 'AVENIDA DE MADRID, 4' a 'Av. de Madrid, 4'."""
    out = []
    for i, w in enumerate(texto.split()):
        lw = w.lower()
        if (re.search(r"\d", w) or re.fullmatch(r"[A-Z]{1,3}-[A-Z0-9]+", w)
                or w in ("S/N", "SN", "N-VI", "A-I", "N-I", "II", "III", "I", "VI")
                or (marca and len(w) <= 3 and w.isalpha())):
            out.append(w)
        elif lw in ("km.", "km"):
            out.append("km")
        elif i > 0 and lw in PEQUENAS:
            out.append(lw)
        else:
            out.append(lw[:1].upper() + lw[1:])
    r = " ".join(out)
    for a, b in (("Carretera", "Ctra."), ("Avenida", "Av."), ("Autovia", "Autovía"),
                 ("Poligono", "Polígono"), ("Calle", "C/")):
        r = re.sub(rf"\b{a}\b", b, r)
    return r


def precio(v):
    return int(round(float(v.replace(",", ".")) * 1000)) if v else 0


def gasolineras():
    print("Descargando precios del Ministerio…")
    try:
        d = descargar_json(API_MINISTERIO)
        filas = []
        for s in d["ListaEESSPrecio"]:
            if s.get("Tipo Venta") != "P":  # solo venta al público
                continue
            filas.append([
                PROVINCIAS[s["IDProvincia"]],
                s["Municipio"].strip(),
                bonito(s["Rótulo"], marca=True),
                bonito(s["Dirección"]),
                s["Horario"].strip(),
                precio(s["Precio Gasolina 95 E5"]) or precio(s["Precio Gasolina 95 E10"]),
                precio(s["Precio Gasoleo A"]),
                precio(s["Precio Gasolina 98 E5"]) or precio(s["Precio Gasolina 98 E10"]),
                round(float(s["Latitud"].replace(",", ".")), 5),
                round(float(s["Longitud (WGS84)"].replace(",", ".")), 5),
            ])
        if len(filas) < 500:
            raise RuntimeError(f"Respuesta sospechosa: solo {len(filas)} gasolineras")
        datos = {"fecha": d["Fecha"], "gasolineras": filas}
        (DATOS / "gasolineras.json").write_text(
            json.dumps(datos, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
        print(f"  {len(filas)} gasolineras, precios del {d['Fecha']}")
        return datos, True
    except Exception as e:  # noqa: BLE001
        print(f"AVISO: uso los últimos precios guardados. Motivo: {e}", file=sys.stderr)
        return json.loads((DATOS / "gasolineras.json").read_text(encoding="utf-8")), False


def puntos_carga():
    print("Descargando puntos de carga de la Junta…")
    try:
        res = []
        for off in (0, 100, 200):
            res += descargar_json(API_JUNTA_CARGA.format(off), intentos=2).get("results", [])
        vistos, out = set(), []
        for x in res:
            if not x.get("dd"):
                continue
            tipos = "/".join(t.replace("Mennekes (Type 2 sin cable)", "Type 2")
                             .replace("Mennekes (Type 2)", "Type 2").replace(" (DC)", "")
                             .replace("CCS Combo", "CCS").replace("COMBO - Cable", "CCS")
                             for t in (x.get("tipo") or []))
            fila = [round(x["dd"]["lat"], 4), round(x["dd"]["lon"], 4), (x.get("nombre") or "").strip(),
                    (x.get("direccion") or "").strip(), (x.get("operador") or "").strip(), tipos]
            k = tuple(fila[:3])
            if k not in vistos:
                vistos.add(k)
                out.append(fila)
        if len(out) > 50:
            (DATOS / "puntos-carga.json").write_text(json.dumps(out, ensure_ascii=False), encoding="utf-8")
            print(f"  {len(out)} puntos de carga")
            return out
    except Exception as e:  # noqa: BLE001
        print(f"AVISO: uso los puntos de carga guardados. Motivo: {e}", file=sys.stderr)
    return json.loads((DATOS / "puntos-carga.json").read_text(encoding="utf-8"))


def fecha_bonita(f):
    # "05/11/2026 18:51:11" -> "5 de noviembre de 2026, 18:51"
    m = re.match(r"(\d+)/(\d+)/(\d+) (\d+):(\d+)", f)
    if not m:
        return f
    d, mes, a, h, mi = m.groups()
    return f"{int(d)} de {MESES[int(mes) - 1]} de {a}, {h}:{mi}"


def main():
    datos, nuevos = gasolineras()
    ev = puntos_carga()
    prov = json.loads((DATOS / "provincias.json").read_text(encoding="utf-8"))
    j = lambda o: json.dumps(o, ensure_ascii=False, separators=(",", ":"))  # noqa: E731

    if SALIDA.exists():
        shutil.rmtree(SALIDA)
    SALIDA.mkdir()

    reemplazos = {
        "__DATA__": j(datos["gasolineras"]),
        "__EV__": j(ev),
        "__PROV__": j(prov),
        "__FECHA__": fecha_bonita(datos["fecha"]),
        "__NTOT__": str(len(datos["gasolineras"])),
        "__URL__": URL_WEB,
    }
    for nombre in ("index.html", "mapa.html"):
        html = (RAIZ / "plantillas" / nombre).read_text(encoding="utf-8")
        for k, v in reemplazos.items():
            html = html.replace(k, v)
        (SALIDA / nombre).write_text(html, encoding="utf-8")

    # Páginas fijas (aviso legal, privacidad, cookies, contacto…) y archivos sueltos
    for f in (RAIZ / "paginas").iterdir():
        if f.is_file():
            shutil.copy(f, SALIDA / f.name)

    paginas = ["", "mapa.html"] + sorted(f.name for f in (RAIZ / "paginas").glob("*.html"))
    (SALIDA / "sitemap.xml").write_text(
        '<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
        + "".join(f"  <url><loc>{URL_WEB}/{p}</loc></url>\n" for p in paginas) + "</urlset>\n", encoding="utf-8")
    (SALIDA / "robots.txt").write_text(f"User-agent: *\nAllow: /\nSitemap: {URL_WEB}/sitemap.xml\n", encoding="utf-8")
    (SALIDA / ".nojekyll").write_text("", encoding="utf-8")

    print(f"Web generada en {SALIDA} ({'precios nuevos' if nuevos else 'precios guardados'})")


if __name__ == "__main__":
    main()
