"""Criterio de aceptación de la 7.2, sobre una foto REAL de producción.

Agarra una foto que una fila de Evidence referencia de verdad, la borra del bucket
principal y la recupera desde el respaldo, comprobando que vuelve byte a byte y que el
`file_url` que ya tiene la base vuelve a funcionar sin tocar ninguna fila.

    python smoke_tests/evidence_restore_real.py

Salvaguardas, en este orden, ANTES de borrar nada:
  1. la foto se copia al respaldo y se verifica el sha256 de la copia;
  2. se baja una copia local a `smoke_tests/.restore-backup/`;
  3. recién ahí se borra del principal.
Si algo falla en el medio, la foto está en dos lugares además del principal, y el
script imprime cómo reponerla a mano.
"""

import hashlib
import os
import sys
import urllib.request
from pathlib import Path

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BASE_DIR)
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

import django  # noqa: E402

django.setup()

from django.conf import settings  # noqa: E402

from ops import evidence_backup as eb  # noqa: E402
from shipments.models import Evidence  # noqa: E402

ok = 0
fallas = []

# El dev URL de R2 (`pub-….r2.dev`) rechaza con 403 los User-Agent que parecen bot:
# con el de urllib da 403 y con uno de navegador da 200. No es un problema del bucket
# ni de la foto — verificado contra fotos que este script no toca.
UA_NAVEGADOR = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120"


def pedir_url_publica(url):
    """(status, cuerpo) del file_url, como lo pediría el navegador del receptor."""
    req = urllib.request.Request(url, headers={"User-Agent": UA_NAVEGADOR})
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            return resp.status, resp.read()
    except urllib.error.HTTPError as exc:
        return exc.code, b""
    except Exception as exc:  # noqa: BLE001
        return f"ERR {exc}", b""


def check(descripcion, condicion, detalle=""):
    global ok
    if condicion:
        ok += 1
        print(f"  OK   {descripcion}")
    else:
        fallas.append(descripcion)
        print(f"  FALLA {descripcion} {detalle}")


print(f"principal: r2://{settings.R2_BUCKET_NAME}")
print(f"respaldo:  r2://{settings.R2_EVIDENCE_BACKUP_BUCKET_NAME}")

# --- Elegir la foto ---------------------------------------------------------

fuente = eb.list_source()
candidatas = [
    (key, pk) for key, pk in sorted(eb.referenced_keys().items()) if key in fuente
]
if not candidatas:
    sys.exit("No hay ninguna foto referenciada por un Evidence en el bucket. Nada que probar.")

# La más chica de todas: si algo sale mal, es la que menos tarda en reponerse.
key, evidence_id = min(candidatas, key=lambda par: fuente[par[0]]["size"])
evidencia = Evidence.objects.get(pk=evidence_id)
print(f"\nfoto elegida: {key}")
print(f"  Evidence #{evidence_id} — remito #{evidencia.shipment_id} — "
      f"{fuente[key]['size']:,} bytes")
print(f"  file_url: {evidencia.file_url}")

origen = eb.get_source_client()
objeto_original = origen.get_object(Bucket=settings.R2_BUCKET_NAME, Key=key)
original = objeto_original["Body"].read()
content_type_original = objeto_original.get("ContentType")
url_original = evidencia.file_url
sha_original = hashlib.sha256(original).hexdigest()
print(f"  sha256:   {sha_original}")

# --- Salvaguardas -----------------------------------------------------------

print("\n=== Salvaguardas antes de borrar ===")

eb.sync()
copia = eb.list_backup()
check("la foto está en el respaldo", key in copia)
check(
    "la copia del respaldo tiene el mismo tamaño",
    copia.get(key, {}).get("size") == len(original),
)

respaldo_obj = eb.get_backup_client().get_object(
    Bucket=settings.R2_EVIDENCE_BACKUP_BUCKET_NAME, Key=eb.backup_key_for(key)
)
bytes_respaldo = respaldo_obj["Body"].read()
check("la copia del respaldo es byte a byte la original", bytes_respaldo == original)

local_dir = Path(BASE_DIR) / "smoke_tests" / ".restore-backup"
local_dir.mkdir(exist_ok=True)
local = local_dir / Path(key).name
local.write_bytes(original)
check("hay una copia local de seguridad", local.exists() and local.stat().st_size == len(original))

if fallas:
    sys.exit("\nNO se borra nada: alguna salvaguarda falló.")

# --- Borrar y detectar ------------------------------------------------------

print("\n=== La foto se pierde del bucket principal ===")
print(f"  (si algo se rompe de acá en más: python manage.py backup_evidence --restore {key})")

origen.delete_object(Bucket=settings.R2_BUCKET_NAME, Key=key)
check("la foto ya NO está en el bucket principal", key not in eb.list_source())

estado, _ = pedir_url_publica(evidencia.file_url)
check("el file_url de la base ahora da 404", estado == 404, f"dio {estado}")

reporte = eb.audit()
perdidas = {p["key"]: p for p in reporte["perdidas"]}
check("la auditoría la detecta como perdida", key in perdidas, sorted(perdidas))
check(
    "la auditoría dice que es recuperable",
    perdidas.get(key, {}).get("recuperable") is True,
)
check("la auditoría la ata a su Evidence", perdidas.get(key, {}).get("evidence_id") == evidence_id)
check("el reporte sale ok=False", reporte["ok"] is False)

# --- Recuperar --------------------------------------------------------------

print("\n=== Recuperación desde el respaldo ===")

tamano, digest = eb.restore_object(key)
check("restore_object la devuelve", tamano == len(original))
check("el sha256 coincide con el original", digest == sha_original)

recuperada = origen.get_object(Bucket=settings.R2_BUCKET_NAME, Key=key)
bytes_recuperados = recuperada["Body"].read()
check("la foto recuperada es byte a byte la original", bytes_recuperados == original)
check(
    "conserva el content type",
    recuperada.get("ContentType") == content_type_original,
    f"{recuperada.get('ContentType')} contra {content_type_original}",
)

estado, cuerpo = pedir_url_publica(evidencia.file_url)
check("el file_url de la base vuelve a servir la foto", estado == 200, f"dio {estado}")
check("lo que sirve la URL pública es byte a byte la original", cuerpo == original)

evidencia.refresh_from_db()
check(
    "no hizo falta tocar la base: el file_url quedó igual que antes de la pérdida",
    evidencia.file_url == url_original,
    f"{evidencia.file_url} contra {url_original}",
)

reporte = eb.audit()
check("la auditoría vuelve a dar ok=True", reporte["ok"] is True, reporte["perdidas"])

# --- Cierre -----------------------------------------------------------------

local.unlink(missing_ok=True)
try:
    local_dir.rmdir()
except OSError:
    pass

print(f"\n{'='*60}\n{ok} OK, {len(fallas)} FALLA(S)")
for f in fallas:
    print(f"  - {f}")
if fallas:
    print(f"\nOJO: revisá que {key} esté en el bucket principal antes de irte.")
sys.exit(1 if fallas else 0)
