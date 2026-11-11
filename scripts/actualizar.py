"""Descarga los precios de las gasolineras de Castilla y León y genera la web.

Uso:  python scripts/actualizar.py
Crea la carpeta  sitio/  con la web lista para publicar.
Solo usa la biblioteca estándar de Python (no hay que instalar nada).
"""
import json
from html import escape as html_escape
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
                precio(s.get("Precio Gases licuados del petróleo", "")),  # 10 autogás (GLP), €/l
                precio(s.get("Precio Adblue", "")),                       # 11 AdBlue, €/l
                precio(s.get("Precio Gas Natural Comprimido", "")),       # 12 gas natural (GNC), €/kg
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
        d = json.loads((DATOS / "gasolineras.json").read_text(encoding="utf-8"))
        for g in d["gasolineras"]:  # datos antiguos sin los combustibles nuevos
            g.extend([0] * (13 - len(g)))
        return d, False


URL_DGT_CARGA = "https://nap.dgt.es/datex2/v3/miterd/EnergyInfrastructureTablePublication/electrolineras.xml"
PROV_CYL = {"Ávila": 0, "Avila": 0, "Burgos": 1, "León": 2, "Leon": 2, "Palencia": 3, "Salamanca": 4,
            "Segovia": 5, "Soria": 6, "Valladolid": 7, "Zamora": 8}
CP_CYL = {"05": 0, "09": 1, "24": 2, "34": 3, "37": 4, "40": 5, "42": 6, "47": 7, "49": 8}


def tipo_conector(t):
    t = t.lower()
    if "combo" in t:
        return "CCS"
    if "chademo" in t:
        return "CHAdeMO"
    if "t2" in t:
        return "Type 2"
    if "t1" in t:
        return "Type 1"
    if "domestic" in t or "schuko" in t:
        return "Schuko"
    if "tesla" in t:
        return "Tesla"
    return t


def puntos_carga():
    """Puntos de carga de Castilla y León desde el Punto de Acceso Nacional de la DGT (CC BY, diario)."""
    print("Descargando puntos de carga de la DGT…")
    try:
        import io
        import xml.etree.ElementTree as ET
        if os.environ.get("SIN_DESCARGA"):
            raise RuntimeError("descarga desactivada (SIN_DESCARGA)")
        req = urllib.request.Request(URL_DGT_CARGA, headers={"User-Agent": "RepostarBaratoCyL/1.0"})
        with urllib.request.urlopen(req, timeout=240) as r:
            crudo = r.read()
        grupos = {}
        for _, el in ET.iterparse(io.BytesIO(crudo), events=("end",)):
            if not el.tag.endswith("}energyInfrastructureSite"):
                continue
            def txt(path):
                x = el.find(path)
                return (x.text or "").strip() if x is not None and x.text else ""
            lineas = {}
            for v in el.findall(".//{*}addressLine//{*}value"):
                if ":" in (v.text or ""):
                    k, val = v.text.split(":", 1)
                    lineas[k.strip()] = val.strip()
            cp = txt(".//{*}postcode")
            prov = PROV_CYL.get(lineas.get("Provincia", ""), CP_CYL.get(cp[:2]))
            if prov is None or not lineas.get("Comunidad Autónoma", "Castilla y León").startswith("Castilla y Le"):
                el.clear()
                continue
            try:
                lat, lon = float(txt(".//{*}latitude")), float(txt(".//{*}longitude"))
            except ValueError:
                el.clear()
                continue
            nombre = txt("./{*}name//{*}value")
            operador = txt("./{*}operator//{*}value")
            tipos, potencia, puntos = set(), 0, 0
            for rp in el.iter():
                if rp.tag.endswith("}refillPoint"):
                    puntos += 1
                elif rp.tag.endswith("}connectorType") and rp.text:
                    tipos.add(tipo_conector(rp.text))
                elif rp.tag.endswith("}maxPowerAtSocket") and rp.text:
                    try:
                        potencia = max(potencia, float(rp.text) / 1000)
                    except ValueError:
                        pass
            municipio = lineas.get("Municipio", "")
            direccion = lineas.get("Dirección", "")
            clave = (round(lat, 4), round(lon, 4), operador)
            g = grupos.setdefault(clave, {"lat": lat, "lon": lon, "nombre": re.sub(r"\s*Estaci[oó]n de carga \d+$", "", nombre) or nombre,
                                          "dir": direccion + (f", {municipio}" if municipio else "") + f" ({NOMBRES_PROV[prov]})",
                                          "op": operador, "tipos": set(), "kw": 0, "n": 0,
                                          "horario": txt(".//{*}operatingHours/{*}label")})
            g["tipos"] |= tipos
            g["kw"] = max(g["kw"], potencia)
            g["n"] += puntos
            el.clear()
        orden = ["CCS", "CHAdeMO", "Type 2", "Type 1", "Schuko", "Tesla"]
        out = [[round(g["lat"], 5), round(g["lon"], 5), g["nombre"], g["dir"], g["op"],
                "/".join(sorted(g["tipos"], key=lambda x: orden.index(x) if x in orden else 99)),
                round(g["kw"]), g["n"], g["horario"]] for g in grupos.values()]
        if len(out) > 200:
            (DATOS / "puntos-carga.json").write_text(json.dumps(out, ensure_ascii=False), encoding="utf-8")
            print(f"  {len(out)} ubicaciones de carga en Castilla y León")
            return out
        raise RuntimeError(f"respuesta sospechosa: {len(out)} ubicaciones")
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
        f"<tr><td>{i + 1}</td><td>{esc(g[2])}<small><a href=\"https://www.google.com/maps/dir/?api=1&amp;destination={g[8]},{g[9]}\" target=\"_blank\" rel=\"noopener\">{esc(g[3])} ↗</a></small></td>"
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
                     "__CUERPO__": cuerpo, "__RUTA__": ruta, "__RAIZ__": raiz, "__RELACIONADOS__": relacionados,
                     "__HEADEXTRA__": head_extra(ruta, titulo, desc, raiz)}.items():
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


# ---------------------------------------------------------------------------
# Páginas por pueblo y por provincia (gasolineras/<pueblo>/ y provincia/<prov>/)
# ---------------------------------------------------------------------------
import math
import unicodedata


def nombre_pueblo(m):
    """'Adrada (La)' -> 'La Adrada'."""
    r = re.match(r"^(.*?)\s*\((La|El|Los|Las|L')\)$", m.strip())
    return f"{r.group(2)} {r.group(1)}" if r else m.strip()


def slug(texto):
    s = unicodedata.normalize("NFD", texto).encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z0-9]+", "-", s).strip("-")


def km(a, b):
    la1, lo1, la2, lo2 = map(math.radians, (a[0], a[1], b[0], b[1]))
    h = math.sin((la2 - la1) / 2) ** 2 + math.cos(la1) * math.cos(la2) * math.sin((lo2 - lo1) / 2) ** 2
    return 12742 * math.asin(math.sqrt(h))


def agrupar_pueblos(G):
    pueblos = {}
    for g in G:
        pueblos.setdefault((g[1], g[0]), []).append(g)
    nombres = [nombre_pueblo(m) for m, _ in pueblos]
    repetidos = {n for n in nombres if nombres.count(n) > 1}
    out = []
    for (m, pr), gs in pueblos.items():
        n = nombre_pueblo(m)
        s = slug(n) + (f"-{slug(NOMBRES_PROV[pr])}" if n in repetidos else "")
        c = (sum(g[8] for g in gs) / len(gs), sum(g[9] for g in gs) / len(gs))
        out.append({"municipio": m, "nombre": n, "prov": pr, "slug": s, "gs": gs, "centro": c})
    return out


def mapa_slugs(G):
    return {f"{p['municipio']}|{p['prov']}": p["slug"] for p in agrupar_pueblos(G)}


def ruta_maps(g):
    return f"https://www.google.com/maps/dir/?api=1&amp;destination={g[8]},{g[9]}"


def tabla_gasolineras(gs, k_orden=5):
    gs = sorted(gs, key=lambda g: (g[k_orden] or 9e9, g[6] or 9e9))
    mins = {k: min((g[k] for g in gs if g[k]), default=0) for k in (5, 6, 7)}
    filas = ""
    for g in gs:
        celdas = ""
        for k in (5, 6, 7):
            if g[k]:
                chip = ' <span class="chip">Más barata</span>' if g[k] == mins[k] and len(gs) > 1 else ""
                celdas += f'<td class="n">{eur(g[k])}{chip}</td>'
            else:
                celdas += '<td><small>—</small></td>'
        filas += (f'<tr><td><strong>{esc(g[2])}</strong><small><a href="{ruta_maps(g)}" target="_blank" rel="noopener">'
                  f'{esc(g[3])} ↗</a></small><small>{esc(g[4])}</small></td>{celdas}</tr>')
    return ('<div class="datos"><div class="tb"><table class="pt"><tr><th>Gasolinera</th><th>Gasolina 95</th><th>Diésel</th>'
            f'<th>Gasolina 98</th></tr>{filas}</table></div></div>')


OTROS = ((10, "Autogás (GLP)", "€/l"), (11, "AdBlue", "€/l"), (12, "Gas natural (GNC)", "€/kg"))


def tabla_otros(gs):
    cols = [c for c in OTROS if any(len(g) > c[0] and g[c[0]] for g in gs)]
    xs = [g for g in gs if any(g[c[0]] for c in cols)]
    if not cols:
        return ""
    cab = "".join(f"<th>{n}</th>" for _, n, _ in cols)
    filas = "".join(
        f'<tr><td><strong>{esc(g[2])}</strong><small><a href="{ruta_maps(g)}" target="_blank" rel="noopener">{esc(g[3])} ↗</a></small></td>'
        + "".join(f'<td class="n">{eur(g[k]).replace(" €", " " + u)}</td>' if g[k] else "<td><small>—</small></td>" for k, _, u in cols)
        + "</tr>" for g in xs)
    return ('<h2>Otros combustibles</h2><div class="datos"><div class="tb"><table class="ot">'
            f'<tr><th>Gasolinera</th>{cab}</tr>{filas}</table></div></div>')


def json_ld(obj):
    return '<script type="application/ld+json">' + json.dumps(obj, ensure_ascii=False) + "</script>"


def generar_pueblos(datos, reemplazos, head_extra):
    G, fecha = datos["gasolineras"], fecha_bonita(datos["fecha"])
    plantilla = (RAIZ / "plantillas" / "pagina.html").read_text(encoding="utf-8")
    pueblos = agrupar_pueblos(G)
    medias_prov = {}
    for i in range(len(NOMBRES_PROV)):
        xs = [g for g in G if g[0] == i]
        medias_prov[i] = {k: media([g[k] for g in xs if g[k]]) for k in (5, 6)}

    def pagina(ruta, raiz, titulo, desc, migas, cuerpo, aside, extra=""):
        html = plantilla
        hx = head_extra(ruta, titulo, desc, raiz) + extra
        for k, v in {**reemplazos, "__TITULO__": esc(titulo), "__DESCRIPCION__": esc(desc), "__RUTA__": ruta,
                     "__RAIZ__": raiz, "__MIGAS__": migas, "__CUERPO__": cuerpo, "__ASIDE__": aside,
                     "__HEADEXTRA__": hx}.items():
            html = html.replace(k, v)
        d = SALIDA / ruta
        d.mkdir(parents=True, exist_ok=True)
        (d / "index.html").write_text(html, encoding="utf-8")

    rutas = []
    for p in pueblos:
        gs, pr, n = p["gs"], p["prov"], p["nombre"]
        np_ = NOMBRES_PROV[pr]
        v95 = sorted(g[5] for g in gs if g[5])
        vdi = sorted(g[6] for g in gs if g[6])
        cercanos = sorted((q for q in pueblos if q is not p), key=lambda q: km(p["centro"], q["centro"]))[:8]
        # texto con datos reales
        frases = [f"En {esc(n)} ({np_}) hay {len(gs)} gasolinera{'s' if len(gs) != 1 else ''} que comunica{'n' if len(gs) != 1 else ''} sus precios al Ministerio."]
        for v, nom, k in ((v95, "gasolina 95", 5), (vdi, "diésel", 6)):
            if not v:
                continue
            m = media(v)
            dif = m - medias_prov[pr][k]
            comp = ("prácticamente igual que" if abs(dif) < 5 else
                    f"{eur(abs(dif))} {'más barato' if dif < 0 else 'más caro'} que")
            frases.append(f"El litro de {nom} cuesta {'de media ' if len(v) > 1 else ''}{eur(m)}"
                          + (f" (de {eur(v[0])} a {eur(v[-1])})" if len(v) > 1 else "")
                          + f", {comp} la media de la provincia de {np_} ({eur(medias_prov[pr][k])}).")
        mejor_cerca = []
        for q in cercanos[:5]:
            qv = [g[5] for g in q["gs"] if g[5]]
            if qv and v95 and min(qv) < v95[0]:
                mejor_cerca.append((q, min(qv)))
        if mejor_cerca:
            q, pv = min(mejor_cerca, key=lambda x: x[1])
            frases.append(f'Si te pilla de camino, en <a href="../{q["slug"]}/">{esc(q["nombre"])}</a>, a unos '
                          f'{round(km(p["centro"], q["centro"]))} km, la gasolina 95 está desde {eur(pv)}.')
        cuerpo = "<p>" + " ".join(frases) + "</p>\n" + tabla_gasolineras(gs) + tabla_otros(gs)
        cuerpo += ('<p>Toca la dirección de cada gasolinera para abrir la ruta en Google Maps. '
                   'Los precios se actualizan dos veces al día con los datos del Ministerio para la Transición Ecológica.</p>')
        lis = "".join(
            f'<li><a href="../{q["slug"]}/">{esc(q["nombre"])}</a><small>{round(km(p["centro"], q["centro"]))} km</small></li>'
            for q in cercanos)
        aside = (f'<aside class="mas"><h2>Pueblos cercanos</h2><ul class="lista">{lis}</ul>'
                 f'<p style="margin-top:16px"><a href="../../provincia/{slug(np_)}/">Ver todas las gasolineras de la provincia de {np_} →</a></p></aside>')
        migas = (f'<a href="../../">Inicio</a> › <a href="../../provincia/{slug(np_)}/">{np_}</a> › {esc(n)}')
        precio_txt = f" Gasolina 95 desde {eur(v95[0])}" if v95 else ""
        precio_txt += f", diésel desde {eur(vdi[0])}" if vdi else ""
        titulo = f"Gasolineras baratas en {n} hoy"
        desc = f"Precio de la gasolina y el diésel hoy en {n} ({np_}).{precio_txt}. {len(gs)} gasolinera{'s' if len(gs) != 1 else ''}, actualizado a diario."
        ld = json_ld({"@context": "https://schema.org", "@graph": [
            {"@type": "BreadcrumbList", "itemListElement": [
                {"@type": "ListItem", "position": 1, "name": "Inicio", "item": URL_WEB + "/"},
                {"@type": "ListItem", "position": 2, "name": np_, "item": f"{URL_WEB}/provincia/{slug(np_)}/"},
                {"@type": "ListItem", "position": 3, "name": n, "item": f"{URL_WEB}/gasolineras/{p['slug']}/"}]},
            {"@type": "ItemList", "itemListElement": [
                {"@type": "ListItem", "position": i + 1, "item": {
                    "@type": "GasStation", "name": g[2],
                    "address": {"@type": "PostalAddress", "streetAddress": g[3], "addressLocality": n,
                                "addressRegion": np_, "addressCountry": "ES"},
                    "geo": {"@type": "GeoCoordinates", "latitude": g[8], "longitude": g[9]}}}
                for i, g in enumerate(gs)]}]})
        ruta = f"gasolineras/{p['slug']}/"
        pagina(ruta, "../../", titulo, desc, migas, cuerpo, aside, ld)
        rutas.append(ruta)

    # Provincias
    for i, np_ in enumerate(NOMBRES_PROV):
        ps = sorted((p for p in pueblos if p["prov"] == i), key=lambda p: slug(p["nombre"]))
        gs = [g for p in ps for g in p["gs"]]
        top = sorted((g for g in gs if g[5]), key=lambda g: g[5])[:15]
        topd = sorted((g for g in gs if g[6]), key=lambda g: g[6])[:15]
        nombre_de = {(p["municipio"], p["prov"]): p for p in ps}

        def tabla_top(xs, k, nom):
            filas = "".join(
                f'<tr><td>{j + 1}</td><td><strong>{esc(g[2])}</strong><small><a href="{ruta_maps(g)}" target="_blank" rel="noopener">{esc(g[3])} ↗</a></small></td>'
                f'<td><a href="../../gasolineras/{nombre_de[(g[1], g[0])]["slug"]}/">{esc(nombre_de[(g[1], g[0])]["nombre"])}</a></td><td class="n">{eur(g[k])}</td></tr>'
                for j, g in enumerate(xs))
            return caja(f"{nom}: las 15 más baratas de {np_}",
                        "<tr><th>#</th><th>Gasolinera</th><th>Pueblo</th><th>Precio</th></tr>" + filas, "", fecha)

        lis = "".join(
            f'<li><a href="../../gasolineras/{p["slug"]}/">{esc(p["nombre"])}</a>'
            f'<small>{eur(min(g[5] for g in p["gs"] if g[5])) if any(g[5] for g in p["gs"]) else ""}</small></li>'
            for p in ps)
        cuerpo = (f"<p>La provincia de {np_} tiene {len(gs)} gasolineras repartidas en {len(ps)} municipios. "
                  f"El precio medio hoy es de {eur(medias_prov[i][5])} el litro de gasolina 95 y "
                  f"{eur(medias_prov[i][6])} el de diésel.</p>"
                  + tabla_top(top, 5, "Gasolina 95") + tabla_top(topd, 6, "Diésel")
                  + f'<h2>Gasolineras por pueblo en {np_}</h2><p>Precio más bajo de gasolina 95 en cada municipio:</p><ul class="lista">{lis}</ul>')
        otras = "".join(f'<li><a href="../{slug(o)}/">{o}</a></li>' for o in NOMBRES_PROV if o != np_)
        aside = f'<aside class="mas"><h2>Otras provincias</h2><ul class="lista">{otras}</ul></aside>'
        ruta = f"provincia/{slug(np_)}/"
        pagina(ruta, "../../", f"Gasolineras baratas en la provincia de {np_} hoy",
               f"Las gasolineras más baratas de {np_} hoy y el precio de la gasolina y el diésel en sus {len(ps)} municipios, actualizado a diario.",
               f'<a href="../../">Inicio</a> › {np_}', cuerpo, aside)
        rutas.append(ruta)

    # Bloque de enlaces para la portada
    bloques = ""
    for i, np_ in enumerate(NOMBRES_PROV):
        ps = sorted((p for p in pueblos if p["prov"] == i), key=lambda p: slug(p["nombre"]))
        lis = "".join(f'<li><a href="gasolineras/{p["slug"]}/">{esc(p["nombre"])}</a></li>' for p in ps)
        bloques += (f'<details><summary>{np_} <span>{len(ps)} pueblos</span></summary>'
                    f'<p><a href="provincia/{slug(np_)}/">Ver las más baratas de {np_} →</a></p><ul class="lista">{lis}</ul></details>\n')
    return rutas, bloques


def head_extra(ruta, titulo, desc, raiz):
    url = f"{URL_WEB}/{ruta}"
    return (f'<link rel="icon" href="{raiz}logo-192.png" type="image/png">\n'
            f'<link rel="apple-touch-icon" href="{raiz}logo-512.png">\n'
            f'<meta property="og:type" content="website">\n<meta property="og:site_name" content="Repostar Barato CyL">\n'
            f'<meta property="og:locale" content="es_ES">\n<meta property="og:url" content="{url}">\n'
            f'<meta property="og:title" content="{esc(titulo)}">\n<meta property="og:description" content="{esc(desc)}">\n'
            f'<meta property="og:image" content="{URL_WEB}/logo-horizontal.png">\n<meta name="twitter:card" content="summary">\n'
            '<link rel="manifest" href="/manifest.webmanifest">\n<meta name="theme-color" content="#121a22">\n'
            '<script>if("serviceWorker" in navigator)addEventListener("load",()=>navigator.serviceWorker.register("/sw.js").catch(()=>{}))</script>')


GA_ID = os.environ.get("GA_ID", "G-E5M5FXVFMY")
GA_TAG = (f'<script async src="https://www.googletagmanager.com/gtag/js?id={GA_ID}"></script>\n'
          '<script>window.dataLayer=window.dataLayer||[];function gtag(){dataLayer.push(arguments)}'
          'gtag("consent","default",{ad_storage:"denied",ad_user_data:"denied",ad_personalization:"denied",analytics_storage:"denied",wait_for_update:500});'
          'gtag("js",new Date());'
          f'gtag("config","{GA_ID}",{{modo:matchMedia("(display-mode: standalone)").matches?"app":"web"}});'
          'addEventListener("appinstalled",()=>gtag("event","app_instalada"));</script>\n')
ADS_MARCA = '<script async src="https://pagead2.googlesyndication.com'


def poner_analytics():
    n = 0
    for f in SALIDA.rglob("*.html"):
        t = f.read_text(encoding="utf-8")
        if ADS_MARCA in t and "googletagmanager.com/gtag" not in t:
            f.write_text(t.replace(ADS_MARCA, GA_TAG + ADS_MARCA, 1), encoding="utf-8")
            n += 1
    print(f"Google Analytics en {n} páginas")


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
    paginas_pueblo, bloques = generar_pueblos(datos, reemplazos, head_extra)
    reemplazos["__CONSEJOS__"] = portada
    reemplazos["__PUEBLOS__"] = bloques
    reemplazos["__SLUGS__"] = j(mapa_slugs(datos["gasolineras"]))
    cabeceras = {
        "index.html": head_extra("", "Gasolineras baratas en Castilla y León hoy",
                                 "Precio de la gasolina y el diésel hoy en todas las gasolineras de Castilla y León, actualizado cada día.", "")
        + json_ld({"@context": "https://schema.org", "@type": "WebSite", "name": "Repostar Barato CyL", "url": URL_WEB + "/",
                   "inLanguage": "es-ES", "publisher": {"@type": "Organization", "name": "Repostar Barato CyL",
                                                         "logo": URL_WEB + "/logo-512.png"}}),
        "mapa.html": head_extra("mapa.html", "Mapa satélite de gasolineras de Castilla y León",
                                "Todas las gasolineras de Castilla y León sobre imágenes de satélite, con sus precios de hoy.", ""),
    }
    for nombre in ("index.html", "mapa.html"):
        html = (RAIZ / "plantillas" / nombre).read_text(encoding="utf-8")
        reemplazos["__HEADEXTRA__"] = cabeceras[nombre]
        for k, v in reemplazos.items():
            html = html.replace(k, v)
        (SALIDA / nombre).write_text(html, encoding="utf-8")

    # Páginas fijas (aviso legal, privacidad, cookies, contacto…) y archivos sueltos
    for f in (RAIZ / "paginas").iterdir():
        if f.is_file():
            shutil.copy(f, SALIDA / f.name)

    legales = sorted(f.name for f in (RAIZ / "paginas").glob("*.html"))
    paginas = ["", "mapa.html"] + paginas_art + paginas_pueblo + [x for x in legales if x == "contacto.html"]
    hoy = time.strftime("%Y-%m-%d")
    (SALIDA / "sitemap.xml").write_text(
        '<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
        + "".join(f"  <url><loc>{URL_WEB}/{p}</loc><lastmod>{hoy}</lastmod></url>\n" for p in paginas)
        + "</urlset>\n", encoding="utf-8")
    (SALIDA / "robots.txt").write_text(f"User-agent: *\nAllow: /\nDisallow: /id-titular.png\nSitemap: {URL_WEB}/sitemap.xml\n", encoding="utf-8")
    (SALIDA / ".nojekyll").write_text("", encoding="utf-8")

    if GA_ID:
        poner_analytics()

    # Modo mantenimiento: en GitHub, variable MANTENIMIENTO = si
    if os.environ.get("MANTENIMIENTO", "").strip().lower() in ("si", "sí", "1", "true", "on"):
        msg = os.environ.get("MENSAJE_MANTENIMIENTO", "").strip() or \
            "Estamos mejorando la web para ofrecerte más información. Volvemos muy pronto con los precios actualizados."
        aviso = (RAIZ / "plantillas" / "mantenimiento.html").read_text(encoding="utf-8").replace("__MENSAJE__", html_escape(msg))
        respetar = {"aviso-legal.html", "privacidad.html", "cookies.html", "contacto.html"}
        for f in SALIDA.rglob("*.html"):
            if f.name not in respetar:
                f.write_text(aviso, encoding="utf-8")
        (SALIDA / "404.html").write_text(aviso, encoding="utf-8")
        print("MODO MANTENIMIENTO ACTIVADO")

    print(f"Web generada en {SALIDA} ({'precios nuevos' if nuevos else 'precios guardados'})")


if __name__ == "__main__":
    main()
