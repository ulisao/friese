"""Prueba en el navegador de las dos pantallas que cambiaron.

- `/alta-operador/{token}`: la pantalla a la que lleva el QR.
- El detalle del operador: motivo de la queja, cierre automático y las fotos de
  la recepción separadas de las del despacho.

Corre contra un backend y un frontend LOCALES (Django en :8000 + Vite en :5173,
que proxea /api). Los datos se crean por la API, como en el uso real, y se borran
al final.
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
from django.core.management import call_command  # noqa: E402
from django.utils import timezone  # noqa: E402

from catalog.models import Product  # noqa: E402
from companies.models import Company  # noqa: E402
from shipments.models import Evidence, Shipment  # noqa: E402
from users.models import OperatorInvite, User  # noqa: E402

from browser import Browser  # noqa: E402
from e2e import check, summary  # noqa: E402

PYTHON = os.path.join(BASE_DIR, "venv", "Scripts", "python.exe")
FRONT = "http://localhost:5173"
API = "http://127.0.0.1:8000/api"
TAG = "SMOKE68"
FOTO = os.path.join(BASE_DIR, "frontend", "public",
                    "WhatsApp Image 2026-08-11 at 12.13.12.jpeg")

procesos = [
    subprocess.Popen([PYTHON, "manage.py", "runserver", "127.0.0.1:8000", "--noreload"],
                     cwd=BASE_DIR, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL),
    subprocess.Popen(["npm.cmd", "run", "dev"], cwd=os.path.join(BASE_DIR, "frontend"),
                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL),
]

company = None
navegador = None
try:
    for url in (f"{API}/public/shipment/00000000-0000-0000-0000-000000000000/", FRONT):
        limite = time.time() + 90
        while time.time() < limite:
            try:
                requests.get(url, timeout=5)
                break
            except Exception:
                time.sleep(0.5)
        else:
            raise RuntimeError(f"no levantó {url}")

    # --- Datos: se arman por la API, igual que en el uso real ------------
    company = Company.objects.create(name=f"Graneles {TAG} SRL", email=f"{TAG.lower()}@friese.test")
    producto = Product.objects.create(company=company, name=f"Maíz {TAG}", unit="ton")
    invite = OperatorInvite.objects.create(
        company=company, expires_at=timezone.now() + timedelta(days=7))

    with open(FOTO, "rb") as fh:
        foto = fh.read()

    op_user, op_pass = f"{TAG.lower()}_op", secrets.token_urlsafe(18)

    navegador = Browser()

    # --- 1. Alta del operador desde el QR --------------------------------
    navegador.goto(f"{FRONT}/alta-operador/{invite.token}")
    navegador.wait("document.querySelector('#username')", label="pantalla de alta")
    navegador.shot("f01-alta-operador")
    check(True, "la pantalla del QR carga sin login")

    navegador.fill("#username", op_user)
    navegador.fill("#password", "1234")
    navegador.fill("#password-confirm", "1234")
    navegador.click("button[type=submit]")
    navegador.wait("document.querySelector('[data-testid=register-error]')",
                   label="error de contraseña débil")
    error = navegador.text("[data-testid=register-error]")
    check("8 caracteres" in error or "corta" in error,
          "una contraseña débil muestra el motivo real, no un error genérico", error[:70])
    navegador.shot("f02-alta-error")

    navegador.fill("#password", op_pass)
    navegador.fill("#password-confirm", op_pass + "x")
    navegador.click("button[type=submit]")
    navegador.wait("document.querySelector('[data-testid=register-error]')", label="error")
    check("no coinciden" in navegador.text("[data-testid=register-error]"),
          "si las contraseñas no coinciden avisa antes de llamar al backend")

    navegador.fill("#password-confirm", op_pass)
    navegador.click("button[type=submit]")
    navegador.wait("location.pathname === '/'", timeout=60, label="entra logueado")
    check(User.objects.filter(username=op_user, company=company,
                              role=User.OPERATOR).exists(),
          "el operador quedó creado en su empresa desde la pantalla del QR")
    check(True, "creada la cuenta, entra directo a la lista sin volver a tipear")
    navegador.shot("f03-alta-ok")

    invite.refresh_from_db()
    check(invite.is_used, "la invitación quedó marcada como usada")

    navegador.goto(f"{FRONT}/alta-operador/{invite.token}")
    navegador.wait("document.querySelector('#username') || location.pathname === '/'",
                   label="alta con token ya usado")
    check(navegador.js("location.pathname") == "/",
          "con la sesión ya abierta, el link del QR lleva a la app y no al alta de nuevo")

    # --- 2. Remitos para el detalle --------------------------------------
    token = requests.post(f"{API}/auth/login/", json={
        "username": op_user, "password": op_pass}, timeout=30).json()["access"]
    auth = {"Authorization": f"Bearer {token}"}

    def json_o_explota(respuesta, que):
        """Si el server contestó otra cosa que JSON, se ve QUÉ contestó."""
        try:
            return respuesta.json()
        except Exception as exc:  # noqa: BLE001
            raise RuntimeError(
                f"{que}: HTTP {respuesta.status_code} — {respuesta.text[:300]}") from exc

    def armar_remito(nombre):
        remito = json_o_explota(
            requests.post(f"{API}/shipments/", headers=auth, json={
                "receiver_name": nombre, "receiver_email": "nadie@friese.test"}, timeout=30),
            "crear remito")
        item = requests.post(f"{API}/shipments/{remito['id']}/items/", headers=auth,
                             json={"product": producto.id, "quantity": "30.00"},
                             timeout=30).json()
        # La foto se ata AL PRODUCTO: es lo que hace el frontend con "Sacar foto de
        # este producto", y es el caso donde el conteo por ítem tiene que ser exacto.
        requests.post(f"{API}/shipments/{remito['id']}/evidence/", headers=auth,
                      files={"file": ("despacho.jpg", foto, "image/jpeg")},
                      data={"shipment_item": item["id"]}, timeout=120)
        despacho = requests.patch(f"{API}/shipments/{remito['id']}/dispatch/",
                                  headers=auth, timeout=60).json()
        requests.get(f"{API}/public/shipment/{despacho['public_token']}/", timeout=30)
        return remito["id"], despacho["public_token"], item["id"]

    # a) En disputa, con motivo y dos fotos del receptor sobre el MISMO producto:
    #    así se ve si el conteo del ítem las suma indebidamente.
    id_disputa, token_disputa, item_disputa = armar_remito(f"Acopio en disputa {TAG}")
    for n in (1, 2):
        requests.post(f"{API}/public/shipment/{token_disputa}/evidence/",
                      files={"file": (f"recepcion{n}.jpg", foto, "image/jpeg")},
                      data={"shipment_item": item_disputa}, timeout=120)
    motivo = "Llegaron 25 toneladas de 30 y la lona venía rota."
    requests.post(f"{API}/public/shipment/{token_disputa}/dispute/",
                  json={"dispute_reason": motivo}, timeout=60)

    # b) Cerrado solo por silencio.
    id_auto, _, _ = armar_remito(f"Acopio sin respuesta {TAG}")
    Shipment.objects.filter(pk=id_auto).update(
        response_deadline=timezone.now() - timedelta(minutes=1))
    call_command("close_expired_shipments")

    # c) Conformidad expresa.
    id_ok, token_ok, _ = armar_remito(f"Acopio conforme {TAG}")
    requests.post(f"{API}/public/shipment/{token_ok}/accept/", timeout=60)

    # --- 3. El detalle del operador --------------------------------------
    navegador.goto(f"{FRONT}/remitos/{id_disputa}")
    navegador.wait("document.querySelector('[data-testid=dispute-panel]')",
                   label="panel de la queja")
    # Las fotos vienen de R2 y tardan: se espera a que estén CARGADAS de verdad
    # (naturalWidth > 0), que es lo que prueba que el operador las ve.
    navegador.wait(
        "[...document.querySelectorAll('img')].length === 3 && "
        "[...document.querySelectorAll('img')].every(i => i.naturalWidth > 0)",
        timeout=90, label="las 3 fotos cargadas desde R2")
    check(True, "las fotos del despacho y de la recepción se ven servidas desde R2")
    navegador.shot("f04-detalle-disputa")
    check(motivo in navegador.text("[data-testid=dispute-reason]"),
          "el operador ve el MOTIVO que escribió el receptor")
    check(navegador.js("document.querySelectorAll('[data-testid=evidence-list] li').length") == 1,
          "las fotos del despacho quedan solas en su grilla")
    check(navegador.js(
        "document.querySelectorAll('[data-testid=reception-evidence-list] li').length") == 2,
        "las 2 fotos de la recepción van en su propia sección")
    cuerpo = navegador.js("document.body.innerText")
    check("Fotos de la carga recibida" in cuerpo and "Fotos del despacho" in cuerpo,
          "cada grilla dice de quién son las fotos")
    # El producto tiene 1 foto de despacho y 2 de recepción: el conteo del ítem
    # tiene que decir 1, no 3.
    check("1 foto de este producto" in cuerpo,
          "el conteo por producto NO suma las 2 fotos del reclamo",
          navegador.js("document.querySelector('[data-item-photos]').innerText"))

    navegador.goto(f"{FRONT}/remitos/{id_auto}")
    navegador.wait("document.querySelector('[data-testid=accepted-panel]')",
                   label="panel de aceptado")
    navegador.shot("f05-detalle-auto")
    check("Cerrado automáticamente" in navegador.text("[data-testid=accepted-panel]"),
          "un remito cerrado por silencio lo dice, en vez de un «Aceptado» a secas")

    navegador.goto(f"{FRONT}/remitos/{id_ok}")
    navegador.wait("document.querySelector('[data-testid=accepted-panel]')", label="conforme")
    navegador.shot("f06-detalle-conforme")
    texto = navegador.text("[data-testid=accepted-panel]")
    check("conforme" in texto and "automáticamente" not in texto,
          "la conformidad expresa se distingue del cierre por silencio", texto[:60])
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
    for proc in procesos:
        proc.terminate()
    for proc in procesos:
        try:
            proc.wait(timeout=10)
        except Exception:
            proc.kill()

sys.exit(summary("pantallas nuevas en el navegador"))
