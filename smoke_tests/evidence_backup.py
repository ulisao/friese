"""Verificación del respaldo de las fotos de evidencia (tarea 7.2).

Prueba el circuito completo contra R2 REAL: copiar, borrar del bucket principal y
recuperar la foto desde el respaldo, comparando los bytes. Es el criterio de
aceptación de la tarea.

    python smoke_tests/evidence_backup.py                  # contra el bucket real
    python smoke_tests/evidence_backup.py --prefijo-prueba # contra friese-backup/evidence-test

La opción `--prefijo-prueba` usa el bucket y el token del backup de la BASE con un
prefijo aparte, para poder ejercitar todo el código antes de que exista el bucket
definitivo. Es privado, así que las fotos no quedan expuestas.

La foto que se borra y se restaura es una SINTÉTICA que sube este mismo script: no se
toca ninguna foto real de un remito.
"""

import hashlib
import io
import os
import sys
import uuid
from datetime import datetime, timedelta, timezone as dt_timezone

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BASE_DIR)

# Estas tienen que estar ANTES de django.setup(): load_dotenv no pisa lo que ya está
# en el entorno, así que lo que se setea acá gana sobre el .env.
if "--prefijo-prueba" in sys.argv:
    from dotenv import dotenv_values

    valores = dotenv_values(os.path.join(BASE_DIR, ".env"))
    os.environ["R2_EVIDENCE_BACKUP_BUCKET_NAME"] = valores.get(
        "R2_BACKUP_BUCKET_NAME", "friese-backup"
    )
    os.environ["R2_EVIDENCE_BACKUP_ACCESS_KEY"] = valores.get("R2_BACKUP_ACCESS_KEY", "")
    os.environ["R2_EVIDENCE_BACKUP_SECRET_KEY"] = valores.get("R2_BACKUP_SECRET_KEY", "")
    os.environ["R2_EVIDENCE_BACKUP_PREFIX"] = "evidence-test"

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

import django  # noqa: E402

django.setup()

from django.conf import settings  # noqa: E402

from ops import evidence_backup as eb  # noqa: E402

ok = 0
fallas = []


def check(descripcion, condicion, detalle=""):
    global ok
    if condicion:
        ok += 1
        print(f"  OK   {descripcion}")
    else:
        fallas.append(descripcion)
        print(f"  FALLA {descripcion} {detalle}")


def titulo(texto):
    print(f"\n=== {texto} ===")


# Un JPEG mínimo pero real (cabecera JFIF + relleno), para que el content type y el
# tamaño se parezcan a los de una foto de verdad.
FOTO = b"\xff\xd8\xff\xe0\x00\x10JFIF\x00\x01\x01\x00\x00\x01\x00\x01\x00\x00" + \
    bytes(range(256)) * 400 + b"\xff\xd9"
SHA_FOTO = hashlib.sha256(FOTO).hexdigest()

print(f"principal: r2://{settings.R2_BUCKET_NAME}")
print(
    f"respaldo:  r2://{settings.R2_EVIDENCE_BACKUP_BUCKET_NAME}"
    f"/{settings.R2_EVIDENCE_BACKUP_PREFIX}"
)

origen = eb.get_source_client()
respaldo = eb.get_backup_client()

# --- 1. Copia incremental de lo que ya hay ----------------------------------

titulo("1. Copia del bucket principal al respaldo")

previo = eb.sync(dry_run=True)
print(f"  (hay {previo['source_total']} objeto(s) en el principal, "
      f"{previo['pending']} sin copiar)")

resultado = eb.sync()
check(
    "sync copia todos los pendientes",
    resultado["copied"] == previo["pending"],
    f"copiados {resultado['copied']} de {previo['pending']}",
)

fuente = eb.list_source()
copia = eb.list_backup()
check(
    "el respaldo tiene todas las keys del principal",
    set(fuente) <= set(copia),
    f"faltan {sorted(set(fuente) - set(copia))[:3]}",
)
check(
    "todos los tamaños coinciden",
    all(copia[k]["size"] == v["size"] for k, v in fuente.items() if k in copia),
)

# El sha256 se guarda en la metadata al copiar: se verifica contra el contenido real.
verificados = 0
for key in list(fuente)[:10]:
    obj = respaldo.get_object(
        Bucket=settings.R2_EVIDENCE_BACKUP_BUCKET_NAME, Key=eb.backup_key_for(key)
    )
    cuerpo = obj["Body"].read()
    guardado = (obj.get("Metadata") or {}).get("sha256")
    if hashlib.sha256(cuerpo).hexdigest() == guardado:
        verificados += 1
check(
    "el sha256 guardado coincide con el contenido de cada copia",
    verificados == min(len(fuente), 10),
    f"{verificados}/{min(len(fuente), 10)}",
)

segunda = eb.sync()
check("una segunda corrida no copia nada (incremental)", segunda["copied"] == 0)

# --- 2. Perder una foto y recuperarla ---------------------------------------

titulo("2. Borrar una foto del principal y recuperarla del respaldo")

key_prueba = f"evidence/0/0/dispatch/{uuid.uuid4().hex}.jpg"
origen.put_object(
    Bucket=settings.R2_BUCKET_NAME,
    Key=key_prueba,
    Body=FOTO,
    ContentType="image/jpeg",
)
print(f"  (foto de prueba: {key_prueba}, {len(FOTO)} bytes)")

nueva = eb.sync()
check("sync copia la foto nueva", key_prueba in nueva["keys"])

respaldada = respaldo.get_object(
    Bucket=settings.R2_EVIDENCE_BACKUP_BUCKET_NAME, Key=eb.backup_key_for(key_prueba)
)
bytes_respaldo = respaldada["Body"].read()
check("la copia es byte a byte la foto original", bytes_respaldo == FOTO)
check(
    "la copia conserva el content type",
    respaldada.get("ContentType") == "image/jpeg",
    respaldada.get("ContentType"),
)

origen.delete_object(Bucket=settings.R2_BUCKET_NAME, Key=key_prueba)
existe = key_prueba in eb.list_source()
check("la foto ya NO está en el bucket principal", not existe)

tamano, digest = eb.restore_object(key_prueba)
check("restore_object devuelve la foto al principal", tamano == len(FOTO))
check("el sha256 restaurado es el original", digest == SHA_FOTO)

recuperada = origen.get_object(Bucket=settings.R2_BUCKET_NAME, Key=key_prueba)
bytes_recuperados = recuperada["Body"].read()
check("la foto recuperada es byte a byte la original", bytes_recuperados == FOTO)
check(
    "la foto recuperada conserva el content type",
    recuperada.get("ContentType") == "image/jpeg",
    recuperada.get("ContentType"),
)

try:
    eb.restore_object(key_prueba)
    check("restaurar sobre una foto que existe NO pisa", False, "no cortó")
except eb.EvidenceBackupError as exc:
    check("restaurar sobre una foto que existe NO pisa", "no se pisa" in str(exc))

# --- 3. El respaldo nunca borra ---------------------------------------------

titulo("3. El respaldo no propaga los borrados")

origen.delete_object(Bucket=settings.R2_BUCKET_NAME, Key=key_prueba)
eb.sync()
check(
    "la copia sigue en el respaldo después de borrar el original y correr sync",
    key_prueba in eb.list_backup(),
)

# --- 4. Auditoría -----------------------------------------------------------

titulo("4. Auditoría (audit) sobre un estado armado")

ahora = datetime.now(dt_timezone.utc)
viejo = ahora - timedelta(hours=48)
reciente = ahora - timedelta(minutes=5)

real_source, real_backup, real_ref = eb.list_source, eb.list_backup, eb.referenced_keys
eb.list_source = lambda: {
    "evidence/1/1/dispatch/copiada.jpg": {"size": 10, "last_modified": viejo},
    "evidence/1/1/dispatch/sin-copia-vieja.jpg": {"size": 10, "last_modified": viejo},
    "evidence/1/1/dispatch/recien-subida.jpg": {"size": 10, "last_modified": reciente},
}
eb.list_backup = lambda: {
    "evidence/1/1/dispatch/copiada.jpg": {"size": 10, "last_modified": viejo},
    "evidence/1/1/dispatch/borrada-recuperable.jpg": {"size": 10, "last_modified": viejo},
    "evidence/1/1/dispatch/basura-de-test.jpg": {"size": 10, "last_modified": viejo},
}
eb.referenced_keys = lambda: {
    "evidence/1/1/dispatch/copiada.jpg": 1,
    "evidence/1/1/dispatch/borrada-recuperable.jpg": 2,
    "evidence/1/1/dispatch/borrada-sin-copia.jpg": 3,
}

reporte = eb.audit()
perdidas = {p["key"]: p for p in reporte["perdidas"]}

check(
    "una foto vieja sin copiar se reporta como sin respaldo",
    reporte["sin_respaldo"] == ["evidence/1/1/dispatch/sin-copia-vieja.jpg"],
    reporte["sin_respaldo"],
)
check(
    "una foto recién subida NO se reporta como falla (espera la próxima corrida)",
    reporte["esperando"] == ["evidence/1/1/dispatch/recien-subida.jpg"],
    reporte["esperando"],
)
check(
    "una foto que la base referencia y ya no está se detecta como perdida",
    set(perdidas) == {
        "evidence/1/1/dispatch/borrada-recuperable.jpg",
        "evidence/1/1/dispatch/borrada-sin-copia.jpg",
    },
    sorted(perdidas),
)
check(
    "la perdida que está en el respaldo figura como recuperable",
    perdidas["evidence/1/1/dispatch/borrada-recuperable.jpg"]["recuperable"] is True,
)
check(
    "la perdida que no está en el respaldo figura como NO recuperable",
    perdidas["evidence/1/1/dispatch/borrada-sin-copia.jpg"]["recuperable"] is False,
)
check(
    "un objeto solo en el respaldo y sin Evidence no es una falla",
    reporte["solo_en_respaldo"] == ["evidence/1/1/dispatch/basura-de-test.jpg"],
    reporte["solo_en_respaldo"],
)
check("el reporte con problemas sale ok=False", reporte["ok"] is False)

eb.list_source = lambda: {
    "evidence/1/1/dispatch/copiada.jpg": {"size": 10, "last_modified": viejo}
}
eb.list_backup = lambda: {
    "evidence/1/1/dispatch/copiada.jpg": {"size": 10, "last_modified": viejo}
}
eb.referenced_keys = lambda: {"evidence/1/1/dispatch/copiada.jpg": 1}
check("con todo en orden el reporte sale ok=True", eb.audit()["ok"] is True)

eb.list_source, eb.list_backup, eb.referenced_keys = real_source, real_backup, real_ref

# --- 5. Deducción de la key desde file_url ----------------------------------

titulo("5. Key deducida desde Evidence.file_url")

base = settings.R2_PUBLIC_BASE_URL.rstrip("/")
check(
    "con la URL pública actual",
    eb.key_from_file_url(f"{base}/evidence/39/26/dispatch/abc.jpg")
    == "evidence/39/26/dispatch/abc.jpg",
)
check(
    "con un dominio propio distinto (pendiente de la 2.4)",
    eb.key_from_file_url("https://evidencia.friese.com.ar/evidence/39/26/dispatch/abc.jpg")
    == "evidence/39/26/dispatch/abc.jpg",
)
check("con una URL que no es del bucket", eb.key_from_file_url("https://otro.com/x.jpg") is None)

# --- Limpieza ---------------------------------------------------------------

titulo("Limpieza")

origen.delete_object(Bucket=settings.R2_BUCKET_NAME, Key=key_prueba)
respaldo.delete_object(
    Bucket=settings.R2_EVIDENCE_BACKUP_BUCKET_NAME, Key=eb.backup_key_for(key_prueba)
)
check("la foto de prueba no quedó en el principal", key_prueba not in eb.list_source())
check("la foto de prueba no quedó en el respaldo", key_prueba not in eb.list_backup())

if "--limpiar-respaldo" in sys.argv:
    # Solo para las corridas con --prefijo-prueba: deja el bucket del backup de la base
    # como estaba. NUNCA se corre contra el respaldo definitivo.
    borradas = 0
    for key in eb.list_backup():
        respaldo.delete_object(
            Bucket=settings.R2_EVIDENCE_BACKUP_BUCKET_NAME, Key=eb.backup_key_for(key)
        )
        borradas += 1
    print(f"  borradas {borradas} copia(s) de prueba del prefijo "
          f"«{settings.R2_EVIDENCE_BACKUP_PREFIX}»")

print(f"\n{'='*60}\n{ok} OK, {len(fallas)} FALLA(S)")
for f in fallas:
    print(f"  - {f}")
sys.exit(1 if fallas else 0)
