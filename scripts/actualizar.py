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
    if os.environ.get("SIN_DESCARGA"):  # para pruebas sin internet
        raise RuntimeError("descarga desactivada (SIN_DESCARGA)")
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
                or (marca and len(w) <= 3 and w.isalpha() and lw not in PEQUENAS)):
            out.append(w)
        elif lw in ("km.", "km"):
            out.append("km")
        elif i > 0 and lw in PEQUENAS:
            out.append(lw)
        else:
            out.append(lw[:1].upper() + lw[1:])
    r = " ".join(out)
    r = re.sub(r"\b(Ctra\.|Carretera|Cr|Crta\.?)\s+(Ctra\.|Carretera)\s*", "Ctra. ", r)
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


# ---------------------------------------------------------------------------
# Artículos (carpeta articulos/). Cada uno lleva una cabecera con título,
# descripción y fecha, y puede incluir bloques de datos que se rellenan
# solos con los precios del día, por ejemplo {{ruta A-6 95}}.
# ---------------------------------------------------------------------------
NOMBRES_PROV = ["Ávila", "Burgos", "León", "Palencia", "Salamanca", "Segovia", "Soria", "Valladolid", "Zamora"]
COMBUSTIBLE = {"95": (5, "Gasolina 95"), "diesel": (6, "Diésel"), "98": (7, "Gasolina 98")}
RUTAS = {
    "A-6": r"\bA-?6\b(?!\d)|\bAP-?6\b|\bN-?VI\b(?!I)|\bN-6\b|Noroeste",
    "A-62": r"\bA-?62\b|\bN-?620\b",
    "A-1": r"\bA-?1\b(?!\d)|\bAP-?1\b|\b[AN]-?I\b(?![IV])|Nacional I\b|Madrid-?Irun",
}
GRUPOS = {
    "Bajo coste": ["Ballenoil", "Plenergy", "Petroprix", "Beroil", "Gasexpress", "Easygas", "Maxpetrol", "Gashome", "Galp&go"],
    "Supermercados": ["Carrefour", "Alcampo", "E.leclerc", "E-leclerc", "E. Leclerc", "Supeco"],
    "Grandes marcas": ["Repsol", "Cepsa", "Moeve", "Galp", "Shell", "BP", "Petronor", "Campsa"],
}


def eur(m):
    return f"{m / 1000:.3f}".replace(".", ",") + " €"


def esc(s):
    s = s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    return re.sub(r"\b([AN]P?)-(\d)", "\\1\u2011\\2", s)  # "A-6" sin partir en dos líneas


def grupo_de(marca):
    for g, ms in GRUPOS.items():
        if any(marca.lower().startswith(m.lower()) for m in ms):
            return g
    return None


def caja(titulo, cuerpo_tabla, pie, fecha):
    return (f'<div class="datos"><div class="cab"><strong>{titulo}</strong><span>Precios del {fecha}</span></div>'
            f'<div class="tb"><table>{cuerpo_tabla}</table></div>'
            + (f'<div class="pie">{pie}</div>' if pie else "") + "</div>")


def w_ruta(G, fecha, ruta, comb="95", n="10"):
    k, nom = COMBUSTIBLE[comb]
    xs = [g for g in G if g[k] and re.search(RUTAS[ruta], g[3], re.I)]
    xs.sort(key=lambda g: g[k])
    if not xs:
        return ""
    filas = "".join(
        f"<tr><td>{i + 1}</td><td>{esc(g[2])}<small>{esc(g[3])}</small></td>"
        f"<td>{esc(g[1])}<small>{NOMBRES_PROV[g[0]]}</small></td><td class=\"n\">{eur(g[k])}</td></tr>"
        for i, g in enumerate(xs[:int(n)]))
    dif = (xs[-1][k] - xs[0][k]) * 50 / 1000
    pie = (f"{len(xs)} gasolineras en la {ruta} y sus vías de servicio dentro de Castilla y León. "
           f"Entre la más barata y la más cara hay {eur(xs[-1][k] - xs[0][k])} por litro, "
           f"unos {dif:.2f} € en un depósito de 50 litros.".replace(f"{dif:.2f}", f"{dif:.2f}".replace(".", ",")))
    return caja(f"{nom}: las {min(int(n), len(xs))} más baratas de la {ruta}",
                "<tr><th>#</th><th>Gasolinera</th><th>Pueblo</th><th>Precio</th></tr>" + filas, pie, fecha)


def por_pueblo(G, k):
    d = {}
    for g in G:
        if g[k]:
            d.setdefault((g[1], g[0]), []).append(g[k])
    return [(pu, pr, min(v), sum(v) / len(v), len(v)) for (pu, pr), v in d.items()]


def w_pueblos(G, fecha, comb="95", orden="baratos", n="10"):
    k, nom = COMBUSTIBLE[comb]
    xs = por_pueblo(G, k)
    xs.sort(key=lambda x: x[3], reverse=(orden == "caros"))
    filas = "".join(
        f"<tr><td>{i + 1}</td><td>{esc(pu)}<small>{NOMBRES_PROV[pr]}</small></td>"
        f"<td class=\"n\">{eur(round(media))}</td><td class=\"n\">{eur(mn)}</td><td>{c}</td></tr>"
        for i, (pu, pr, mn, media, c) in enumerate(xs[:int(n)]))
    tit = f"{nom}: los {n} pueblos {'más baratos' if orden == 'baratos' else 'más caros'}"
    return caja(tit, "<tr><th>#</th><th>Pueblo</th><th>Precio medio</th><th>Más barata</th><th>Gasolineras</th></tr>" + filas,
                "Precio medio de todas las gasolineras del pueblo que venden este combustible.", fecha)


def media(v):
    return round(sum(v) / len(v)) if v else 0


def w_marcas(G, fecha):
    filas = ""
    for g in list(GRUPOS) + ["Resto"]:
        xs = [x for x in G if (grupo_de(x[2]) or "Resto") == g]
        filas += (f"<tr><td>{g}</td><td class=\"n\">{eur(media([x[5] for x in xs if x[5]]))}</td>"
                  f"<td class=\"n\">{eur(media([x[6] for x in xs if x[6]]))}</td><td>{len(xs)}</td></tr>")
    return caja("Precio medio según el tipo de gasolinera",
                "<tr><th>Tipo</th><th>Gasolina 95</th><th>Diésel</th><th>Gasolineras</th></tr>" + filas,
                "Bajo coste: " + ", ".join(GRUPOS["Bajo coste"][:6]) + " y similares. Grandes marcas: "
                + ", ".join(GRUPOS["Grandes marcas"]) + ".", fecha)


def w_provincias(G, fecha):
    filas = ""
    for i, n in enumerate(NOMBRES_PROV):
        xs = [x for x in G if x[0] == i]
        a95, adi = media([x[5] for x in xs if x[5]]), media([x[6] for x in xs if x[6]])
        filas += (f"<tr><td>{n}</td><td class=\"n\">{eur(a95)}</td><td class=\"n\">{eur(adi)}</td>"
                  f"<td class=\"n\">{eur(adi - a95) if adi >= a95 else '−' + eur(a95 - adi)}</td></tr>")
    return caja("Precio medio por provincia",
                "<tr><th>Provincia</th><th>Gasolina 95</th><th>Diésel</th><th>Diésel − gasolina</th></tr>" + filas,
                "Si la última columna es negativa, el diésel sale más barato que la gasolina 95.", fecha)


def w_resumen(G, fecha):
    out = '<div class="cifra">'
    for k, nom in ((5, "Gasolina 95"), (6, "Diésel")):
        v = sorted(x[k] for x in G if x[k])
        out += (f"<div><b>{eur(v[0])}</b><span>{nom}: la más barata</span></div>"
                f"<div><b>{eur(media(v))}</b><span>{nom}: precio medio</span></div>")
    return out + "</div>"


WIDGETS = {"ruta": w_ruta, "pueblos": w_pueblos, "marcas": w_marcas, "provincias": w_provincias, "resumen": w_resumen}


def leer_articulos():
    arts = []
    for f in sorted((RAIZ / "articulos").glob("*.html")):
        txt = f.read_text(encoding="utf-8")
        m = re.match(r"\s*<!--(.*?)-->\s*", txt, re.S)
        meta = dict(l.split(":", 1) for l in m.group(1).strip().splitlines() if ":" in l)
        meta = {k.strip(): v.strip() for k, v in meta.items()}
        arts.append({**meta, "slug": f.stem, "cuerpo": txt[m.end():]})
    arts.sort(key=lambda a: (a.get("publicado", ""), -int(a.get("orden", 0))), reverse=True)
    return arts


def fecha_corta(iso):
    a, m, d = iso.split("-")
    return f"{int(d)} de {MESES[int(m) - 1]} de {a}"


def generar_articulos(datos, reemplazos):
    G, fecha = datos["gasolineras"], fecha_bonita(datos["fecha"])
    arts = leer_articulos()
    plantilla = (RAIZ / "plantillas" / "articulo.html").read_text(encoding="utf-8")
    por_slug = {a["slug"]: a for a in arts}

    def rellenar(cuerpo):
        return re.sub(r"\{\{(\w+)([^}]*)\}\}", lambda m: WIDGETS[m.group(1)](G, fecha, *m.group(2).split()), cuerpo)

    def pagina(titulo, desc, publicado, cuerpo, ruta, raiz, relacionados):
        html = plantilla
        for k, v in {**reemplazos, "__TITULO__": esc(titulo), "__DESCRIPCION__": esc(desc), "__PUBLICADO__": publicado,
                     "__CUERPO__": cuerpo, "__RUTA__": ruta, "__RAIZ__": raiz, "__RELACIONADOS__": relacionados}.items():
            html = html.replace(k, v)
        return html

    for a in arts:
        rel = [por_slug[s.strip()] for s in a.get("relacionados", "").split(",") if s.strip() in por_slug]
        rel += [x for x in arts if x is not a and x not in rel][: max(0, 3 - len(rel))]
        li = "".join(f'    <li><a href="../{r["slug"]}/">{esc(r["titulo"])}</a></li>\n' for r in rel[:3])
        d = SALIDA / "consejos" / a["slug"]
        d.mkdir(parents=True, exist_ok=True)
        (d / "index.html").write_text(pagina(a["titulo"], a["descripcion"], fecha_corta(a["publicado"]),
                                             rellenar(a["cuerpo"]), f"consejos/{a['slug']}/", "../../", li), encoding="utf-8")

    tarjetas = "".join(
        f'<h2><a href="{a["slug"]}/" style="color:inherit;text-decoration:none">{esc(a["titulo"])}</a></h2>'
        f'<p>{esc(a["descripcion"])} <a href="{a["slug"]}/">Leer →</a></p>' for a in arts)
    d = SALIDA / "consejos"
    d.mkdir(exist_ok=True)
    hoy = time.strftime("%Y-%m-%d")
    (d / "index.html").write_text(pagina("Consejos para ahorrar en gasolina",
        "Guías con los precios reales de hoy para gastar menos en cada depósito en Castilla y León.",
        fecha_corta(hoy), tarjetas, "consejos/", "../", ""), encoding="utf-8")

    portada = "".join(
        f'      <article><a href="consejos/{a["slug"]}/"><h3>{esc(a["titulo"])}</h3><p>{esc(a["descripcion"])}</p>'
        f'<span class="lee">Leer →</span></a></article>\n' for a in arts[:3])
    return portada, ["consejos/"] + [f"consejos/{a['slug']}/" for a in arts]


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
    portada, paginas_art = generar_articulos(datos, reemplazos)
    reemplazos["__CONSEJOS__"] = portada
    for nombre in ("index.html", "mapa.html"):
        html = (RAIZ / "plantillas" / nombre).read_text(encoding="utf-8")
        for k, v in reemplazos.items():
            html = html.replace(k, v)
        (SALIDA / nombre).write_text(html, encoding="utf-8")

    # Páginas fijas (aviso legal, privacidad, cookies, contacto…) y archivos sueltos
    for f in (RAIZ / "paginas").iterdir():
        if f.is_file():
            shutil.copy(f, SALIDA / f.name)

    paginas = ["", "mapa.html"] + paginas_art + sorted(f.name for f in (RAIZ / "paginas").glob("*.html"))
    (SALIDA / "sitemap.xml").write_text(
        '<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
        + "".join(f"  <url><loc>{URL_WEB}/{p}</loc></url>\n" for p in paginas) + "</urlset>\n", encoding="utf-8")
    (SALIDA / "robots.txt").write_text(f"User-agent: *\nAllow: /\nSitemap: {URL_WEB}/sitemap.xml\n", encoding="utf-8")
    (SALIDA / ".nojekyll").write_text("", encoding="utf-8")

    print(f"Web generada en {SALIDA} ({'precios nuevos' if nuevos else 'precios guardados'})")


if __name__ == "__main__":
    main()
