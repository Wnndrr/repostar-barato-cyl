"""Crea o actualiza en Cloudflare el servidor de "Alerta Chollo" (Worker + almacén KV).

Se ejecuta desde GitHub Actions con los secretos CLOUDFLARE_API_TOKEN, CLOUDFLARE_ACCOUNT_ID y VAPID_PRIVATE_KEY.
Al terminar escribe datos/avisos.json con la dirección del servidor, que la web usa para guardar los avisos.
"""
import hashlib
import json
import os
import sys
import urllib.error
import urllib.request
import uuid
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
API = "https://api.cloudflare.com/client/v4"
NOMBRE = "repostar-avisos"
TOKEN = os.environ.get("CLOUDFLARE_API_TOKEN", "").strip()
CUENTA = os.environ.get("CLOUDFLARE_ACCOUNT_ID", "").strip()
VAPID = os.environ.get("VAPID_PRIVATE_KEY", "").strip()
ORS_KEY = os.environ.get("ORS_API_KEY", "").strip()


def llamar(metodo, ruta, datos=None, cuerpo=None, tipo="application/json"):
    if datos is not None:
        cuerpo = json.dumps(datos).encode()
    req = urllib.request.Request(API + ruta, data=cuerpo, method=metodo)
    req.add_header("Authorization", "Bearer " + TOKEN)
    if cuerpo is not None:
        req.add_header("Content-Type", tipo)
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            return json.loads(r.read() or b"{}")
    except urllib.error.HTTPError as e:
        txt = e.read().decode(errors="replace")
        print(f"Cloudflare respondió {e.code} a {metodo} {ruta}: {txt[:800]}")
        try:
            return json.loads(txt)
        except ValueError:
            return {"success": False}


def main():
    faltan = [n for n, v in [("CLOUDFLARE_API_TOKEN", TOKEN), ("CLOUDFLARE_ACCOUNT_ID", CUENTA), ("VAPID_PRIVATE_KEY", VAPID)] if not v]
    if faltan:
        print("Faltan secretos en GitHub:", ", ".join(faltan), "→ no se despliega el servidor de avisos.")
        return 0
    admin = hashlib.sha256(("repostar-avisos:" + VAPID).encode()).hexdigest()

    # 1) Almacén KV
    r = llamar("GET", f"/accounts/{CUENTA}/storage/kv/namespaces?per_page=100")
    if not r.get("success"):
        sys.exit("No se pudo leer la cuenta de Cloudflare. Revisa el token (plantilla 'Editar Cloudflare Workers') y el ID de cuenta.")
    ns = next((n["id"] for n in r["result"] if n["title"] == NOMBRE), None)
    if not ns:
        r = llamar("POST", f"/accounts/{CUENTA}/storage/kv/namespaces", {"title": NOMBRE})
        if not r.get("success"):
            sys.exit("No se pudo crear el almacén KV.")
        ns = r["result"]["id"]
        print("Almacén KV creado")

    # 2) Código del Worker con sus enlaces (KV y clave de administración)
    meta = {
        "main_module": "worker.js",
        "compatibility_date": "2024-11-01",
        "bindings": [
            {"type": "kv_namespace", "name": "KV", "namespace_id": ns},
            {"type": "secret_text", "name": "ADMIN", "text": admin},
        ] + ([{"type": "secret_text", "name": "ORS", "text": ORS_KEY}] if ORS_KEY else []),
    }
    print("Rutas (openrouteservice):", "con clave" if ORS_KEY else "sin clave todavía, la web usará el modo aproximado")
    limite = "----" + uuid.uuid4().hex
    codigo = (RAIZ / "worker" / "worker.js").read_bytes()
    partes = [
        f'--{limite}\r\nContent-Disposition: form-data; name="metadata"\r\nContent-Type: application/json\r\n\r\n'.encode()
        + json.dumps(meta).encode() + b"\r\n",
        f'--{limite}\r\nContent-Disposition: form-data; name="worker.js"; filename="worker.js"\r\nContent-Type: application/javascript+module\r\n\r\n'.encode()
        + codigo + b"\r\n",
        f"--{limite}--\r\n".encode(),
    ]
    r = llamar("PUT", f"/accounts/{CUENTA}/workers/scripts/{NOMBRE}", cuerpo=b"".join(partes),
               tipo=f"multipart/form-data; boundary={limite}")
    if not r.get("success"):
        sys.exit("No se pudo subir el servidor de avisos.")
    print("Servidor de avisos subido")

    # 3) Dirección pública *.workers.dev
    r = llamar("GET", f"/accounts/{CUENTA}/workers/subdomain")
    sub = (r.get("result") or {}).get("subdomain") if r.get("success") else None
    if not sub:
        for intento in ["repostarbaratocyl", "repostar-barato-cyl", "repostar-cyl-" + uuid.uuid4().hex[:6]]:
            r = llamar("PUT", f"/accounts/{CUENTA}/workers/subdomain", {"subdomain": intento})
            if r.get("success"):
                sub = intento
                print("Subdominio workers.dev creado:", sub)
                break
    if not sub:
        sys.exit("No se pudo crear la dirección workers.dev. Entra en Cloudflare → Workers y Pages una vez para activarla.")
    llamar("POST", f"/accounts/{CUENTA}/workers/scripts/{NOMBRE}/subdomain", {"enabled": True, "previews_enabled": False})
    url = f"https://{NOMBRE}.{sub}.workers.dev"

    destino = RAIZ / "datos" / "avisos.json"
    nuevo = {"url": url}
    if not destino.exists() or json.loads(destino.read_text(encoding="utf-8")) != nuevo:
        destino.write_text(json.dumps(nuevo, indent=2), encoding="utf-8")
    print("Servidor de avisos listo en", url)
    return 0


if __name__ == "__main__":
    sys.exit(main())
