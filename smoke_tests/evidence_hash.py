"""Criterio de aceptación de la 8.1 — el SHA-256 de cada foto de evidencia.

Sube fotos de verdad por los DOS endpoints (despacho del operador y recepción del
receptor por el link público), las baja del bucket y comprueba que el `file_hash`
guardado es exactamente el SHA-256 del archivo, verificado también con una herramienta
externa al proceso de Python (`certutil -hashfile ... SHA256`).

    python smoke_tests/evidence_hash.py

Levanta su propio server local contra la base y el bucket de siempre, crea sus datos
con la marca SMOKE81 y los borra al final (base y R2).
"""

import hashlib
import os
import re
import secrets
import subprocess
import sys
import time
from pathlib import Path

import django
import requests

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE_DIR)
sys.path.insert(0, HERE)
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
django.setup()

from django.conf import settings  # noqa: E402
from django.contrib.auth.hashers import make_password  # noqa: E402

from catalog.models import Product  # noqa: E402
from companies.models import Company  # noqa: E402
from shipments.models import Evidence, Shipment  # noqa: E402
from shipments.storage import get_r2_client  # noqa: E402
from users.models import User  # noqa: E402

from e2e import borrar_historial, check, summary  # noqa: E402

PYTHON = os.path.join(BASE_DIR, "venv", "Scripts", "python.exe")
PUERTO = 8023
LOCAL = f"http://127.0.0.1:{PUERTO}"
API = f"{LOCAL}/api"
TAG = "SMOKE81"
FOTO = os.path.join(BASE_DIR, "frontend", "public",
                    "WhatsApp Image 2026-08-11 at 12.13.12.jpeg")
# El dev URL de R2 rechaza con 403 los User-Agent que parecen bot (ver la nota en
# evidence_restore_real.py): se pide con el de un navegador, que es el caso real.
UA_NAVEGADOR = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120"
HEX64 = re.compile(r"^[0-9a-f]{64}$")


def key_de(file_url):
    """Key del objeto en el bucket a partir del file_url guardado."""
    base = settings.R2_PUBLIC_BASE_URL.rstrip("/") + "/"
    return file_url[len(base):] if file_url.startswith(base) else None


def bajar_de_r2(cliente, file_url):
    """Bytes del objeto tal como están guardados en el bucket."""
    obj = cliente.get_object(Bucket=settings.R2_BUCKET_NAME, Key=key_de(file_url))
    return obj["Body"].read()


def sha256_con_certutil(contenido, nombre):
    """SHA-256 calculado por una herramienta EXTERNA (certutil de Windows).

    Es la verificación independiente que pide la tarea: si el hash guardado coincide
    con el que saca otra implementación sobre el archivo bajado del bucket, no hay
    forma de que el valor venga de un error compartido con el hashlib del server.
    """
    carpeta = Path(HERE) / ".hash-check"
    carpeta.mkdir(exist_ok=True)
    archivo = carpeta / nombre
    archivo.write_bytes(contenido)
    try:
        salida = subprocess.run(
            ["certutil", "-hashfile", str(archivo), "SHA256"],
            capture_output=True, text=True, timeout=60,
        ).stdout
        for linea in salida.splitlines():
            limpia = linea.strip().replace(" ", "").lower()
            if HEX64.match(limpia):
                return limpia
        return f"NO PARSEADO: {salida.strip()[:120]}"
    finally:
        archivo.unlink(missing_ok=True)
        try:
            carpeta.rmdir()
        except OSError:
            pass


proc = subprocess.Popen([PYTHON, "manage.py", "runserver", f"127.0.0.1:{PUERTO}", "--noreload"],
                        cwd=BASE_DIR, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

company = None
try:
    limite = time.time() + 60
    while time.time() < limite:
        try:
            requests.get(f"{LOCAL}/admin/login/", timeout=5)
            break
        except Exception:
            time.sleep(0.4)

    # --- Datos de prueba --------------------------------------------------
    company = Company.objects.create(name=f"Fletes {TAG} SA", email=f"{TAG.lower()}@friese.test")
    op_pass = secrets.token_urlsafe(18)
    User.objects.create(
        username=f"{TAG.lower()}_op", password=make_password(op_pass),
        company=company, role=User.OPERATOR, is_active=True,
    )
    producto = Product.objects.create(company=company, name=f"Bolsas {TAG}", unit="bolsas")

    r = requests.post(f"{API}/auth/login/", json={
        "username": f"{TAG.lower()}_op", "password": op_pass}, timeout=30)
    check(r.status_code == 200, "el operador de prueba puede entrar", f"HTTP {r.status_code}")
    auth = {"Authorization": f"Bearer {r.json()['access']}"}

    with open(FOTO, "rb") as fh:
        foto = fh.read()
    sha_local = hashlib.sha256(foto).hexdigest()
    print(f"\nfoto de prueba: {len(foto):,} bytes")
    print(f"  sha256 del archivo que se manda: {sha_local}")

    remito = requests.post(f"{API}/shipments/", headers=auth,
                           json={"receiver_name": f"Recepción {TAG}",
                                 "receiver_email": "nadie@friese.test"}, timeout=30).json()
    requests.post(f"{API}/shipments/{remito['id']}/items/", headers=auth,
                  json={"product": producto.id, "quantity": "1.00"}, timeout=30)

    cliente = get_r2_client()

    # --- 1. Evidencia de DESPACHO (operador autenticado) -------------------
    print("\n=== Foto de despacho (operador) ===")
    # Se manda un file_hash inventado en el payload: no tiene que llegar a la base.
    r = requests.post(f"{API}/shipments/{remito['id']}/evidence/", headers=auth,
                      files={"file": ("despacho.jpg", foto, "image/jpeg")},
                      data={"file_hash": "0" * 64}, timeout=180)
    check(r.status_code == 201, "la foto de despacho sube", f"HTTP {r.status_code} {r.text[:90]}")
    cuerpo = r.json()
    check(HEX64.match(cuerpo.get("file_hash") or "") is not None,
          "la respuesta trae file_hash de 64 hex", cuerpo.get("file_hash"))
    check(cuerpo["file_hash"] == sha_local,
          "el file_hash de la respuesta es el SHA-256 del archivo que se subió",
          f"{cuerpo.get('file_hash')} contra {sha_local}")

    despacho = Evidence.objects.get(pk=cuerpo["id"])
    check(despacho.file_hash == sha_local, "el hash guardado en la base es el del archivo",
          despacho.file_hash)
    check(despacho.file_hash != "0" * 64,
          "el hash falso que mandó el cliente se ignoró (lo calcula el servidor)")
    check(bool(despacho.file_url) and bool(despacho.uploaded_at),
          "el hash quedó guardado junto al file_url y el uploaded_at del mismo registro")

    bytes_r2 = bajar_de_r2(cliente, despacho.file_url)
    check(len(bytes_r2) == len(foto), "el objeto del bucket pesa lo mismo que el original",
          f"{len(bytes_r2):,} contra {len(foto):,}")
    check(hashlib.sha256(bytes_r2).hexdigest() == despacho.file_hash,
          "el SHA-256 del archivo BAJADO DE R2 coincide con el hash guardado")

    externo = sha256_con_certutil(bytes_r2, "despacho.jpg")
    check(externo == despacho.file_hash,
          "certutil (herramienta externa) saca el mismo hash sobre el archivo bajado",
          f"{externo} contra {despacho.file_hash}")

    publica = requests.get(despacho.file_url, headers={"User-Agent": UA_NAVEGADOR}, timeout=60)
    check(publica.status_code == 200 and hashlib.sha256(publica.content).hexdigest() == despacho.file_hash,
          "lo que sirve el file_url público también da ese hash", f"HTTP {publica.status_code}")

    # Misma foto otra vez: objeto distinto en el bucket, mismo hash de contenido.
    r = requests.post(f"{API}/shipments/{remito['id']}/evidence/", headers=auth,
                      files={"file": ("despacho2.jpg", foto, "image/jpeg")}, timeout=180)
    check(r.status_code == 201, "sube una segunda foto de despacho", f"HTTP {r.status_code}")
    otra = r.json()
    check(otra["file_url"] != cuerpo["file_url"] and otra["file_hash"] == sha_local,
          "el hash es del CONTENIDO: la misma foto en otra key da el mismo hash")

    # Un archivo distinto tiene que dar otro hash (que el hash no sea fijo).
    distinta = foto + b"\x00distinta"
    r = requests.post(f"{API}/shipments/{remito['id']}/evidence/", headers=auth,
                      files={"file": ("otra.jpg", distinta, "image/jpeg")}, timeout=180)
    check(r.status_code == 201 and r.json()["file_hash"] == hashlib.sha256(distinta).hexdigest(),
          "una foto con otro contenido da su propio hash", r.json().get("file_hash"))

    # Foto GRANDE: arriba de FILE_UPLOAD_MAX_MEMORY_SIZE (2,5 MB) Django ya no la trae
    # en memoria sino como TemporaryUploadedFile en disco, que es el caso real de una
    # foto de celular (3-5 MB). Es el camino donde un seek() mal puesto rompería todo:
    # el hash se calcularía bien y a R2 subirían 0 bytes.
    grande = foto + os.urandom(4 * 1024 * 1024)
    sha_grande = hashlib.sha256(grande).hexdigest()
    r = requests.post(f"{API}/shipments/{remito['id']}/evidence/", headers=auth,
                      files={"file": ("grande.jpg", grande, "image/jpeg")}, timeout=300)
    check(r.status_code == 201, "sube una foto de 4 MB (llega como archivo temporal en disco)",
          f"HTTP {r.status_code} {r.text[:90]}")
    grande_ev = Evidence.objects.get(pk=r.json()["id"])
    check(grande_ev.file_hash == sha_grande, "el hash de la foto grande es el del archivo",
          f"{grande_ev.file_hash} contra {sha_grande}")
    bytes_r2 = bajar_de_r2(cliente, grande_ev.file_url)
    check(bytes_r2 == grande,
          "la foto grande llegó COMPLETA a R2, byte a byte (el rebobinado funciona)",
          f"{len(bytes_r2):,} bytes en el bucket contra {len(grande):,} enviados")

    # --- 2. Evidencia de RECEPCIÓN (receptor, endpoint público) ------------
    print("\n=== Foto de recepción (receptor, link público) ===")
    requests.patch(f"{API}/shipments/{remito['id']}/dispatch/", headers=auth, timeout=120)
    token_publico = Shipment.objects.get(pk=remito["id"]).public_token
    requests.get(f"{API}/public/shipment/{token_publico}/", timeout=30)

    r = requests.post(f"{API}/public/shipment/{token_publico}/evidence/",
                      files={"file": ("recepcion.jpg", foto, "image/jpeg")},
                      data={"file_hash": "f" * 64}, timeout=180)
    check(r.status_code == 201, "el receptor sube su foto", f"HTTP {r.status_code} {r.text[:90]}")
    recepcion = Evidence.objects.get(pk=r.json()["id"])
    check(recepcion.type == Evidence.RECEPTION and recepcion.file_hash == sha_local,
          "la evidencia de recepción también queda con su hash calculado", recepcion.file_hash)
    check(recepcion.file_hash != "f" * 64,
          "el endpoint público tampoco acepta un hash del cliente")
    check("file_hash" not in r.json(),
          "el serializer del receptor no expone el hash (expone lo mínimo, tarea 3.1)",
          sorted(r.json()))

    bytes_r2 = bajar_de_r2(cliente, recepcion.file_url)
    check(hashlib.sha256(bytes_r2).hexdigest() == recepcion.file_hash,
          "el SHA-256 del archivo de recepción bajado de R2 coincide con el guardado")
    externo = sha256_con_certutil(bytes_r2, "recepcion.jpg")
    check(externo == recepcion.file_hash,
          "certutil confirma el hash de la foto de recepción",
          f"{externo} contra {recepcion.file_hash}")

    # --- 3. Ninguna evidencia nueva sin hash ------------------------------
    total = Evidence.objects.filter(shipment_id=remito["id"]).count()
    sin_hash = Evidence.objects.filter(shipment_id=remito["id"], file_hash="").count()
    check(sin_hash == 0, f"las {total} fotos de este remito tienen hash", f"{sin_hash} sin hash")
finally:
    # --- Limpieza: base y R2 ---------------------------------------------
    if company:
        ids = list(Shipment.objects.filter(company=company).values_list("id", flat=True))
        ids_usuarios = list(User.objects.filter(company=company).values_list("id", flat=True))
        for file_url in Evidence.objects.filter(
                shipment_id__in=ids).values_list("file_url", flat=True):
            key = key_de(file_url)
            if key:
                get_r2_client().delete_object(Bucket=settings.R2_BUCKET_NAME, Key=key)
        Evidence.objects.filter(shipment_id__in=ids).delete()
        Shipment.objects.filter(company=company).delete()
        Product.objects.filter(company=company).delete()
        User.objects.filter(company=company).delete()
        Company.objects.filter(pk=company.pk).delete()
        # El historial (8.2) no se va con su objeto: hay que limpiarlo aparte.
        borrar_historial(empresas=[company.pk], usuarios=ids_usuarios, remitos=ids)
    proc.terminate()
    try:
        proc.wait(timeout=10)
    except Exception:
        proc.kill()

print(f"\n  limpieza: quedan {Evidence.objects.count()} evidencias y "
      f"{Company.objects.count()} empresas (las de siempre)")
sys.exit(summary("hash SHA-256 de la evidencia (8.1)"))
