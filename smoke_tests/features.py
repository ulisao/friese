"""Prueba local de los tres cambios nuevos, contra un server real corriendo acá.

1. Alta de operador por QR: la URL y el QR que muestra el admin, y la pantalla
   del frontend consumiendo el endpoint.
2. Límite de tamaño de las fotos de evidencia (operador y receptor).
3. (el detalle del operador se prueba en el navegador, en ui_features.py)

Crea sus propios datos con la marca SMOKE67 y los borra al final.
"""

import os
import secrets
import subprocess
import sys
import time
from datetime import timedelta

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
from django.utils import timezone  # noqa: E402

from catalog.models import Product  # noqa: E402
from companies.models import Company  # noqa: E402
from shipments.models import Evidence, Shipment  # noqa: E402
from users.invites import build_invite_qr_svg, build_invite_url  # noqa: E402
from users.models import OperatorInvite, User  # noqa: E402

from e2e import check, summary  # noqa: E402

PYTHON = os.path.join(BASE_DIR, "venv", "Scripts", "python.exe")
PUERTO = 8021
LOCAL = f"http://127.0.0.1:{PUERTO}"
API = f"{LOCAL}/api"
TAG = "SMOKE67"
FOTO = os.path.join(BASE_DIR, "frontend", "public",
                    "WhatsApp Image 2026-08-11 at 12.13.12.jpeg")

proc = subprocess.Popen([PYTHON, "manage.py", "runserver", f"127.0.0.1:{PUERTO}", "--noreload"],
                        cwd=BASE_DIR, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

company = admin_user = None
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
    admin_pass = secrets.token_urlsafe(18)
    admin_user = User.objects.create(
        username=f"{TAG.lower()}_root", password=make_password(admin_pass),
        is_staff=True, is_superuser=True, is_active=True,
    )
    producto = Product.objects.create(company=company, name=f"Bolsas {TAG}", unit="bolsas")
    invite = OperatorInvite.objects.create(
        company=company, expires_at=timezone.now() + timedelta(days=7))

    # --- 1. QR y link de alta --------------------------------------------
    url = build_invite_url(invite.token)
    check(url == f"{settings.FRONTEND_PUBLIC_URL.rstrip('/')}/alta-operador/{invite.token}",
          "el link de alta apunta a la pantalla del frontend con el token", url)
    svg = build_invite_qr_svg(invite.token)
    check(svg.startswith("<svg") and "path" in svg and len(svg) > 500,
          "el QR se genera como SVG (sin Pillow)", f"{len(svg)} bytes")

    sesion = requests.Session()
    sesion.get(f"{LOCAL}/admin/login/", timeout=30)
    sesion.post(f"{LOCAL}/admin/login/", data={
        "username": admin_user.username, "password": admin_pass,
        "csrfmiddlewaretoken": sesion.cookies["csrftoken"], "next": "/admin/"},
        headers={"Referer": f"{LOCAL}/admin/login/"}, timeout=30)
    ficha = sesion.get(f"{LOCAL}/admin/users/operatorinvite/{invite.pk}/change/", timeout=30)
    check(ficha.status_code == 200 and url in ficha.text,
          "la ficha del invite en el admin muestra el link de alta")
    check("<svg" in ficha.text and "Escanealo con la cámara" in ficha.text,
          "la ficha del invite muestra el QR embebido")

    # --- 2. Alta del operador con ese token -------------------------------
    op_pass = secrets.token_urlsafe(18)
    r = requests.post(f"{API}/auth/register-operator/", json={
        "token": str(invite.token), "username": f"{TAG.lower()}_op", "password": op_pass}, timeout=30)
    check(r.status_code == 201, "el alta con el token del QR funciona", f"HTTP {r.status_code}")
    r = requests.post(f"{API}/auth/login/", json={
        "username": f"{TAG.lower()}_op", "password": op_pass}, timeout=30)
    check(r.status_code == 200, "el operador recién creado puede entrar")
    auth = {"Authorization": f"Bearer {r.json()['access']}"}

    invite.refresh_from_db()
    check(invite.is_used, "la invitación queda usada")
    ficha = sesion.get(f"{LOCAL}/admin/users/operatorinvite/{invite.pk}/change/", timeout=30)
    check("YA FUE USADA" in ficha.text,
          "el admin avisa que el QR de una invitación usada ya no sirve")

    # Errores del alta, que son los que ve el operador en pantalla.
    r = requests.post(f"{API}/auth/register-operator/", json={
        "token": str(invite.token), "username": "otro", "password": op_pass}, timeout=30)
    check(r.status_code == 400 and "ya fue utilizada" in r.text,
          "reusar el QR da un mensaje claro", r.text[:70])
    vencida = OperatorInvite.objects.create(
        company=company, expires_at=timezone.now() - timedelta(minutes=1))
    r = requests.post(f"{API}/auth/register-operator/", json={
        "token": str(vencida.token), "username": "otro", "password": op_pass}, timeout=30)
    check(r.status_code == 400 and "expiró" in r.text, "una invitación vencida da 400", r.text[:70])
    r = requests.post(f"{API}/auth/register-operator/", json={
        "token": "00000000-0000-0000-0000-000000000000", "username": "otro",
        "password": op_pass}, timeout=30)
    check(r.status_code == 400, "un token inventado da 400", r.text[:70])
    r = requests.post(f"{API}/auth/register-operator/", json={
        "token": str(OperatorInvite.objects.create(
            company=company, expires_at=timezone.now() + timedelta(days=1)).token),
        "username": "x", "password": "1234"}, timeout=30)
    check(r.status_code == 400 and ("corta" in r.text or "común" in r.text or "numér" in r.text),
          "una contraseña débil se rechaza con el motivo", r.text[:90])

    # --- 3. Límite de tamaño de las fotos ---------------------------------
    with open(FOTO, "rb") as fh:
        chica = fh.read()
    grande = chica + b"\0" * (settings.MAX_EVIDENCE_UPLOAD_MB * 1024 * 1024 + 1)

    remito = requests.post(f"{API}/shipments/", headers=auth,
                           json={"receiver_name": f"Recepción {TAG}",
                                 "receiver_email": "nadie@friese.test"}, timeout=30).json()
    requests.post(f"{API}/shipments/{remito['id']}/items/", headers=auth,
                  json={"product": producto.id, "quantity": "1.00"}, timeout=30)

    r = requests.post(f"{API}/shipments/{remito['id']}/evidence/", headers=auth,
                      files={"file": ("gigante.jpg", grande, "image/jpeg")}, timeout=300)
    check(r.status_code == 400 and "no puede pesar más de" in r.text,
          "el operador NO puede subir una foto que pase el límite",
          f"HTTP {r.status_code} {r.text[:90]}")
    check(Evidence.objects.filter(shipment_id=remito["id"]).count() == 0,
          "la foto rechazada no dejó ningún Evidence en la base")

    r = requests.post(f"{API}/shipments/{remito['id']}/evidence/", headers=auth,
                      files={"file": ("normal.jpg", chica, "image/jpeg")}, timeout=120)
    check(r.status_code == 201, "una foto de tamaño normal sigue subiendo",
          f"HTTP {r.status_code}")

    requests.patch(f"{API}/shipments/{remito['id']}/dispatch/", headers=auth, timeout=60)
    token_publico = Shipment.objects.get(pk=remito["id"]).public_token
    requests.get(f"{API}/public/shipment/{token_publico}/", timeout=30)
    r = requests.post(f"{API}/public/shipment/{token_publico}/evidence/",
                      files={"file": ("gigante.jpg", grande, "image/jpeg")}, timeout=300)
    check(r.status_code == 400 and "no puede pesar más de" in r.text,
          "el RECEPTOR tampoco puede subir una foto que pase el límite (endpoint público)",
          f"HTTP {r.status_code} {r.text[:90]}")
    r = requests.post(f"{API}/public/shipment/{token_publico}/evidence/",
                      files={"file": ("normal.jpg", chica, "image/jpeg")}, timeout=120)
    check(r.status_code == 201, "el receptor sigue pudiendo subir una foto normal",
          f"HTTP {r.status_code}")
finally:
    # --- Limpieza: base y R2 ---------------------------------------------
    if company:
        ids = list(Shipment.objects.filter(company=company).values_list("id", flat=True))
        from shipments.storage import get_r2_client
        cliente = get_r2_client()
        base = settings.R2_PUBLIC_BASE_URL.rstrip("/") + "/"
        for file_url in Evidence.objects.filter(shipment_id__in=ids).values_list("file_url", flat=True):
            if file_url.startswith(base):
                cliente.delete_object(Bucket=settings.R2_BUCKET_NAME, Key=file_url[len(base):])
        Evidence.objects.filter(shipment_id__in=ids).delete()
        Shipment.objects.filter(company=company).delete()
        Product.objects.filter(company=company).delete()
        OperatorInvite.objects.filter(company=company).delete()
        User.objects.filter(company=company).delete()
        Company.objects.filter(pk=company.pk).delete()
    if admin_user:
        User.objects.filter(pk=admin_user.pk).delete()
    proc.terminate()
    try:
        proc.wait(timeout=10)
    except Exception:
        proc.kill()

print(f"\n  limpieza: quedan {Company.objects.count()} empresas y "
      f"{User.objects.count()} usuarios (los de siempre)")
sys.exit(summary("alta por QR + límite de tamaño"))
