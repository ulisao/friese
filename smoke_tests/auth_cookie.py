"""Tarea 6.7 — verificación del refresh token en cookie httpOnly + CSP.

Corre contra el BUILD DE PRODUCCIÓN del frontend, servido con la CSP real de
vercel.json y con la API en el mismo origen (smoke_tests/csp_server.py), y contra
un Django local.

Los criterios de aceptación de la tarea:
  - document.cookie y localStorage NO exponen el refresh token
  - la sesión sobrevive a recargar la página
  - el logout invalida la sesión (un refresh posterior da 401)
  - un refresh desde otro origen no recibe la cookie
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
from django.utils import timezone  # noqa: E402

from catalog.models import Product  # noqa: E402
from companies.models import Company  # noqa: E402
from shipments.models import Evidence, Shipment  # noqa: E402
from users.models import OperatorInvite, User  # noqa: E402

from browser import Browser  # noqa: E402
from csp_server import servir  # noqa: E402
from e2e import check, summary  # noqa: E402

PYTHON = os.path.join(BASE_DIR, "venv", "Scripts", "python.exe")
FRONT = "http://127.0.0.1:5174"
API = "http://127.0.0.1:8000/api"
TAG = "SMOKE70"

django_proc = subprocess.Popen(
    [PYTHON, "manage.py", "runserver", "127.0.0.1:8000", "--noreload"],
    cwd=BASE_DIR, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
servidor = servir(5174)

company = navegador = None
try:
    limite = time.time() + 90
    while time.time() < limite:
        try:
            requests.get(f"{API}/public/shipment/00000000-0000-0000-0000-000000000000/", timeout=5)
            break
        except Exception:
            time.sleep(0.5)

    company = Company.objects.create(name=f"Sesiones {TAG} SA", email=f"{TAG.lower()}@friese.test")
    Product.objects.create(company=company, name=f"Trigo {TAG}", unit="ton")
    op_user, op_pass = f"{TAG.lower()}_op", secrets.token_urlsafe(18)
    User.objects.create_user(username=op_user, password=op_pass, company=company,
                             role=User.OPERATOR)

    # --- 1. El contrato del login, por HTTP -------------------------------
    sesion = requests.Session()
    r = sesion.post(f"{API}/auth/login/", json={"username": op_user, "password": op_pass},
                    timeout=30)
    check(r.status_code == 200, "login OK", f"HTTP {r.status_code}")
    check("access" in r.json(), "el login devuelve el access token")
    check("refresh" not in r.json(), "el login YA NO devuelve el refresh en el cuerpo",
          str(list(r.json())))

    cookie = r.headers.get("Set-Cookie", "")
    check(settings.REFRESH_COOKIE_NAME in cookie, "el refresh vuelve como cookie", cookie[:60])
    check("HttpOnly" in cookie, "la cookie es HttpOnly (JavaScript no la puede leer)")
    check("SameSite=Lax" in cookie, "la cookie es SameSite=Lax")
    check(f"Path={settings.REFRESH_COOKIE_PATH}" in cookie,
          f"la cookie solo viaja a {settings.REFRESH_COOKIE_PATH}", cookie)
    # En desarrollo NO va Secure a propósito (http://localhost no la guardaría).
    check(("Secure" in cookie) == settings.IS_PRODUCTION,
          "Secure sigue al ambiente (en producción sí, en desarrollo no)")

    # --- 2. Refresh sin mandar nada en el cuerpo --------------------------
    r = sesion.post(f"{API}/auth/refresh/", timeout=30)
    check(r.status_code == 200 and "access" in r.json(),
          "el refresh funciona SIN mandar el token: lo toma de la cookie",
          f"HTTP {r.status_code}")
    check("refresh" not in r.json(), "el refresh tampoco devuelve el token en el cuerpo")

    sin_cookie = requests.Session()
    r = sin_cookie.post(f"{API}/auth/refresh/", timeout=30)
    check(r.status_code == 401, "sin cookie, el refresh da 401", f"HTTP {r.status_code}")
    r = sin_cookie.post(f"{API}/auth/refresh/", json={"refresh": "lo-que-sea"}, timeout=30)
    check(r.status_code == 401,
          "mandar un refresh en el cuerpo ya no sirve: la única fuente es la cookie",
          f"HTTP {r.status_code}")

    # --- 3. Logout --------------------------------------------------------
    r = sesion.post(f"{API}/auth/logout/", timeout=30)
    check(r.status_code == 205, "el logout responde 205", f"HTTP {r.status_code}")
    r = sesion.post(f"{API}/auth/refresh/", timeout=30)
    check(r.status_code == 401, "después del logout, el refresh da 401 (token blacklisteado)",
          f"HTTP {r.status_code}")

    # --- 4. En el navegador, con el build real y la CSP puesta ------------
    navegador = Browser()
    navegador.goto(f"{FRONT}/login")
    navegador.wait("document.querySelector('#username')", label="login")
    navegador.fill("#username", op_user)
    navegador.fill("#password", op_pass)
    navegador.click("button[type=submit]")
    navegador.wait("location.pathname === '/'", timeout=60, label="entra a la app")
    check(True, "el operador entra desde el build de producción, con la CSP activa")

    galletas = navegador.js("document.cookie")
    almacen = navegador.js("JSON.stringify(Object.entries(localStorage))")
    check(settings.REFRESH_COOKIE_NAME not in (galletas or ""),
          "document.cookie NO expone el refresh token", f"document.cookie = «{galletas}»")
    check("refresh" not in (almacen or "").lower(),
          "localStorage NO guarda ningún refresh token", almacen[:120])
    check("friese.username" in (almacen or ""),
          "en localStorage solo queda el nombre de usuario, que no es una credencial",
          almacen[:120])

    # La sesión sobrevive a recargar: el access está solo en memoria, así que
    # revivirla depende exclusivamente de la cookie.
    navegador.goto(f"{FRONT}/")
    navegador.wait("location.pathname === '/' && "
                   "!document.body.innerText.includes('Ingresá con tu usuario')",
                   timeout=60, label="sesión revivida")
    check(navegador.js("location.pathname") == "/",
          "recargando la página la sesión sigue viva (la revive la cookie)")
    navegador.shot("c01-sesion-revivida")

    # Con la sesión revivida por la cookie, la app tiene que poder pegarle a la
    # API autenticada: entrar al alta de remito carga el catálogo con el access
    # token nuevo.
    navegador.goto(f"{FRONT}/remitos/nuevo")
    navegador.wait("document.querySelector('#receiver-name')", timeout=60, label="alta de remito")
    check(navegador.js("location.pathname") == "/remitos/nuevo",
          "con la sesión revivida, las llamadas autenticadas a la API funcionan")

    # --- 4b. El flujo con cámara, bajo la CSP -----------------------------
    # Es lo que más riesgo corre con una CSP estricta: el visor usa getUserMedia,
    # la foto sale de un <canvas> y la preview es un blob:. Si la política estuviera
    # mal, esto es lo primero que se rompe.
    navegador.fill("#receiver-name", f"Acopio {TAG}")
    navegador.click("button[data-product-id]")
    navegador.wait("document.querySelector('#item-quantity')", label="cantidad")
    navegador.fill("#item-quantity", "12")
    navegador.js("[...document.querySelectorAll('button')]"
                 ".find(x => x.innerText.trim() === 'Agregar producto').click()")
    navegador.wait("document.querySelector('[data-testid=shipment-items]')", label="ítem")
    navegador.click("button[type=submit]")
    navegador.wait("location.pathname === '/'", timeout=60, label="vuelta a la lista")
    navegador.click_js(
        "[...document.querySelectorAll('a[href^=\"/remitos/\"]')]"
        ".find(a => /\\/remitos\\/\\d+$/.test(a.getAttribute('href')))",
        label="detalle del remito nuevo")
    navegador.wait("document.querySelector('[data-testid=open-camera]')", label="detalle")

    navegador.click("[data-testid=open-camera]")
    navegador.wait("document.querySelector('video') && document.querySelector('video').videoWidth > 0",
                   timeout=60, label="stream de la cámara")
    check(True, "la cámara en vivo abre con la CSP puesta")
    navegador.click("[data-testid=camera-shutter]")
    navegador.wait("document.querySelector('[data-testid=evidence-list] img')",
                   timeout=60, label="preview de la foto")
    check(True, "la preview en blob: se muestra (img-src blob: alcanza)")
    navegador.wait("document.querySelector('[data-testid=evidence-list] img[src^=\"https://pub-\"]')",
                   timeout=180, label="foto confirmada por el backend")
    check(True, "la foto sube a R2 y se ve servida desde ahí (img-src del bucket alcanza)")
    navegador.shot("c03-camara-con-csp")

    # --- 5. Salir ---------------------------------------------------------
    navegador.goto(f"{FRONT}/")
    navegador.wait("document.querySelector('a[href=\"/remitos/nuevo\"]')", label="lista")
    navegador.js("[...document.querySelectorAll('button')]"
                 ".find(b => b.innerText.trim() === 'Salir').click()")
    navegador.wait("location.pathname === '/login'", timeout=60, label="vuelve al login")
    check(True, "el botón Salir cierra la sesión y vuelve al login")
    navegador.goto(f"{FRONT}/")
    navegador.wait("location.pathname === '/login'", timeout=60, label="sigue deslogueado")
    check(True, "después de salir, la app ya no revive ninguna sesión")
    navegador.shot("c02-logout")

    # --- 6. CSP: que no haya roto nada ------------------------------------
    errores = [e for e in navegador.errores_de_consola() if "Content Security Policy" in e]
    check(not errores, "ninguna violación de CSP en el flujo completo",
          " | ".join(errores)[:200] if errores else "0 violaciones")
finally:
    if navegador:
        navegador.close()
    if company:
        ids = list(Shipment.objects.filter(company=company).values_list("id", flat=True))
        # También se borran los objetos de R2: si no, la foto de la prueba queda
        # para siempre en el bucket sin ninguna fila que la referencie.
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
    servidor.shutdown()
    django_proc.terminate()
    try:
        django_proc.wait(timeout=10)
    except Exception:
        django_proc.kill()

sys.exit(summary("refresh en cookie httpOnly + CSP"))
