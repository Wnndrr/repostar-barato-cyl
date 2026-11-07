# Repostar Barato CyL

Web con los precios de la gasolina y el diésel en las gasolineras de Castilla y León, un mapa por precios y los puntos de carga para coches eléctricos.

## Cómo funciona

- `scripts/actualizar.py` descarga los precios del Ministerio (datos abiertos) y genera la web en la carpeta `sitio/`.
- `.github/workflows/actualizar.yml` lo ejecuta dos veces al día y publica la web en GitHub Pages.
- Si el Ministerio no responde, la web se genera con los últimos precios guardados en `datos/`.

## Archivos que puedes editar

- `plantillas/index.html` y `plantillas/mapa.html`: diseño de la web.
- `paginas/`: aviso legal, privacidad, cookies, contacto y `ads.txt`. Rellena los datos marcados como `[...]`.

## Pendiente antes de pedir AdSense

1. Rellenar los datos del titular en `paginas/`.
2. Comprar un dominio y crear `paginas/CNAME` con el dominio dentro.
3. Pegar el código de AdSense donde pone `ADSENSE` en las plantillas y la línea de `ads.txt`.
4. Publicar artículos propios.

Fuentes: Ministerio para la Transición Ecológica y el Reto Demográfico; Junta de Castilla y León.
