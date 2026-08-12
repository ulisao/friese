"""Verificación EN PRODUCCIÓN de los tres cambios recién deployados.

Lo que agrega sobre las pruebas locales: que el deploy realmente los tenga (por
ejemplo que `qrcode` esté instalado en Railway), que Vercel sirva la ruta nueva
y que todo eso funcione con el CORS y el HTTPS reales.

Crea sus propios datos con la marca SMOKE69 y los borra al final, igual que el
smoke test de la 6.6.
"""

import os
import secrets
import sys
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
from users.invites import build_invite_url  # noqa: E402
from users.models import OperatorInvite, User  # noqa: E402

from browser import Browser  # noqa: E402
from e2e import API, BACKEND, FRONTEND, admin_login, check, summary  # noqa: E402

TAG = "SMOKE69"
FOTO = os.path.join(BASE_DIR, "frontend", "public",
                    "WhatsApp Image 2026-08-11 at 12.13.12.jpeg")

company = root = None
navegador = None
try:
    company = Company.objects.create(name=f"Cargas {TAG} SA", email=f"{TAG.lower()}@friese.test")
    producto = Product.objects.create(company=company, name=f"Soja {TAG}", unit="ton")
    invite = OperatorInvite.objects.create(
        company=company, expires_at=timezone.now() + timedelta(days=7))
    root_pass = secrets.token_urlsafe(18)
    root = User.objects.create(username=f"{TAG.lower()}_root", password=make_password(root_pass),
                               is_staff=True, is_superuser=True, is_active=True)

    # --- 1. El QR, en el admin de PRODUCCIÓN ------------------------------
    sesion, respuesta = admin_login(root.username, root_pass)
    check(respuesta.status_code == 302, "login al admin de producción")
    ficha = sesion.get(f"{BACKEND}/admin/users/operatorinvite/{invite.pk}/change/", timeout=30)
    check(ficha.status_code == 200,
          "la ficha del invite abre en producción (o sea: qrcode quedó instalado)",
          f"HTTP {ficha.status_code}")
    url_alta = build_invite_url(invite.token)
    check(url_alta in ficha.text, "el admin muestra el link de alta", url_alta)
    check("<svg" in ficha.text, "el admin muestra el QR embebido")

    # --- 2. El operador se da de alta escaneando el QR --------------------
    navegador = Browser()
    navegador.goto(url_alta)
    navegador.wait("document.querySelector('#username')", label="pantalla de alta en producción")
    check(True, "la URL del QR abre la pantalla de alta en producción (ruteo del SPA en Vercel)")
    navegador.shot("p01-alta-produccion")

    op_user, op_pass = f"{TAG.lower()}_op", secrets.token_urlsafe(18)
    navegador.fill("#username", op_user)
    navegador.fill("#password", op_pass)
    navegador.fill("#password-confirm", op_pass)
    navegador.click("button[type=submit]")
    navegador.wait("location.pathname === '/'", timeout=90, label="entra logueado")
    check(User.objects.filter(username=op_user, company=company, role=User.OPERATOR).exists(),
          "el operador quedó creado contra el backend de producción")
    navegador.shot("p02-alta-ok-produccion")

    # --- 3. Un remito en disputa, para ver el detalle ---------------------
    token = requests.post(f"{API}/auth/login/", json={
        "username": op_user, "password": op_pass}, timeout=30).json()["access"]
    auth = {"Authorization": f"Bearer {token}"}
    with open(FOTO, "rb") as fh:
        foto = fh.read()

    remito = requests.post(f"{API}/shipments/", headers=auth, json={
        "receiver_name": f"Acopio {TAG}", "receiver_email": "nadie@friese.test"},
        timeout=30).json()
    item = requests.post(f"{API}/shipments/{remito['id']}/items/", headers=auth,
                         json={"product": producto.id, "quantity": "40.00"}, timeout=30).json()
    requests.post(f"{API}/shipments/{remito['id']}/evidence/", headers=auth,
                  files={"file": ("despacho.jpg", foto, "image/jpeg")},
                  data={"shipment_item": item["id"]}, timeout=180)
    despacho = requests.patch(f"{API}/shipments/{remito['id']}/dispatch/",
                              headers=auth, timeout=60).json()
    publico = despacho["public_token"]
    requests.get(f"{API}/public/shipment/{publico}/", timeout=30)

    # --- 4. El límite de tamaño, en el endpoint PÚBLICO de producción -----
    grande = foto + b"\0" * (settings.MAX_EVIDENCE_UPLOAD_MB * 1024 * 1024 + 1)
    r = requests.post(f"{API}/public/shipment/{publico}/evidence/",
                      files={"file": ("gigante.jpg", grande, "image/jpeg")}, timeout=300)
    check(r.status_code == 400 and "no puede pesar más de" in r.text,
          "producción rechaza una foto que pasa el límite en el endpoint público",
          f"HTTP {r.status_code} {r.text[:90]}")

    for n in (1, 2):
        r = requests.post(f"{API}/public/shipment/{publico}/evidence/",
                          files={"file": (f"recepcion{n}.jpg", foto, "image/jpeg")},
                          data={"shipment_item": item["id"]}, timeout=180)
        check(r.status_code == 201, f"la foto de recepción {n} sube normal", f"HTTP {r.status_code}")

    motivo = "Faltaron 8 toneladas y el precinto venía cortado."
    r = requests.post(f"{API}/public/shipment/{publico}/dispute/",
                      json={"dispute_reason": motivo}, timeout=60)
    check(r.status_code == 200, "la queja quedó registrada en producción")

    # --- 5. El detalle del operador, en producción ------------------------
    navegador.goto(f"{FRONTEND}/remitos/{remito['id']}")
    navegador.wait("document.querySelector('[data-testid=dispute-panel]')",
                   timeout=60, label="panel de la queja")
    navegador.wait("[...document.querySelectorAll('img')].length === 3 && "
                   "[...document.querySelectorAll('img')].every(i => i.naturalWidth > 0)",
                   timeout=120, label="las 3 fotos cargadas desde R2")
    navegador.shot("p03-detalle-disputa-produccion")
    check(motivo in navegador.text("[data-testid=dispute-reason]"),
          "el operador ve el motivo de la queja en producción")
    check(navegador.js(
        "document.querySelectorAll('[data-testid=reception-evidence-list] li').length") == 2,
        "las fotos del receptor van en su propia sección")
    check("1 foto de este producto" in navegador.js("document.body.innerText"),
          "el conteo por producto no suma las del reclamo")
finally:
    if navegador:
        navegador.close()
    if company:
        ids = list(Shipment.objects.filter(company=company).values_list("id", flat=True))
        from shipments.storage import get_r2_client
        cliente = get_r2_client()
        base = settings.R2_PUBLIC_BASE_URL.rstrip("/") + "/"
        for file_url in Evidence.objects.filter(
                shipment_id__in=ids).values_list("file_url", flat=True):
            if file_url.startswith(base):
                cliente.delete_object(Bucket=settings.R2_BUCKET_NAME, Key=file_url[len(base):])
        Evidence.objects.filter(shipment_id__in=ids).delete()
        Shipment.objects.filter(company=company).delete()
        Product.objects.filter(company=company).delete()
        OperatorInvite.objects.filter(company=company).delete()
        User.objects.filter(company=company).delete()
        Company.objects.filter(pk=company.pk).delete()
    if root:
        User.objects.filter(pk=root.pk).delete()

print(f"\n  limpieza: quedan {Company.objects.count()} empresas, {User.objects.count()} usuarios, "
      f"{Shipment.objects.count()} remitos")
sys.exit(summary("los tres cambios, en producción"))
