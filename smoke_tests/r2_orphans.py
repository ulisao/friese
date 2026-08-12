"""Objetos de R2 que ya no tiene referenciados ninguna fila de Evidence.

Sirve de control después de las pruebas: la evidencia es el corazón del producto,
así que el bucket no debería juntar archivos huérfanos de corridas de test.
Solo LISTA; borrar es con --borrar y únicamente lo que se le pasa por prefijo.
"""

import os
import sys

import django

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BASE_DIR)
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
django.setup()

from django.conf import settings  # noqa: E402

from shipments.models import Evidence  # noqa: E402
from shipments.storage import get_r2_client  # noqa: E402

cliente = get_r2_client()
base = settings.R2_PUBLIC_BASE_URL.rstrip("/") + "/"

referenciados = {
    url[len(base):] for url in Evidence.objects.values_list("file_url", flat=True)
    if url.startswith(base)
}

objetos = []
token = None
while True:
    kwargs = {"Bucket": settings.R2_BUCKET_NAME}
    if token:
        kwargs["ContinuationToken"] = token
    respuesta = cliente.list_objects_v2(**kwargs)
    objetos.extend(respuesta.get("Contents", []))
    if not respuesta.get("IsTruncated"):
        break
    token = respuesta.get("NextContinuationToken")

huerfanos = [o for o in objetos if o["Key"] not in referenciados]

print(f"objetos en el bucket: {len(objetos)}")
print(f"referenciados por un Evidence: {len(referenciados)}")
print(f"HUÉRFANOS: {len(huerfanos)}")
for o in sorted(huerfanos, key=lambda x: x["LastModified"]):
    print(f"  {o['LastModified']:%Y-%m-%d %H:%M}  {o['Size']:>9,} B  {o['Key']}")

if "--borrar" in sys.argv:
    prefijo = sys.argv[sys.argv.index("--borrar") + 1]
    a_borrar = [o for o in huerfanos if o["Key"].startswith(prefijo)]
    for o in a_borrar:
        cliente.delete_object(Bucket=settings.R2_BUCKET_NAME, Key=o["Key"])
    print(f"\nborrados {len(a_borrar)} huérfanos con prefijo «{prefijo}»")
