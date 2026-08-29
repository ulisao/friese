"""Criterio de aceptación de la 10.5 — favicon, título de pestaña y emails con marca.

Dos cosas: que la pestaña del navegador muestre el favicon de Friese y un título
propio en CADA pantalla, y que los emails transaccionales lleguen con identidad
visual, no como texto pelado.

    python smoke_tests/branding.py

Levanta el backend en :8000 y el Vite en :5173. El email se prueba de las dos maneras:
los cinco cuerpos se arman con las funciones REALES, y además se manda UNO de verdad por
Resend y se lee de vuelta por su API, o sea el HTML que salió. Crea sus datos con la
marca SMOKE105 y los borra al final, historial incluido (8.2).
"""

import json
import os
import secrets
import subprocess
import sys
import time
import urllib.request
import uuid
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

from companies.models import Company  # noqa: E402
from shipments.emails import (  # noqa: E402
    _auto_close_email_content,
    _dispatch_email_content,
    _dispute_email_content,
    _reminder_email_content,
    build_public_link,
    send_dispatch_email,
)
from shipments.models import Shipment  # noqa: E402
from users.emails import _reset_email_content  # noqa: E402
from users.models import User  # noqa: E402

from browser import Browser  # noqa: E402
from e2e import borrar_historial, check, summary  # noqa: E402

PYTHON = os.path.join(BASE_DIR, "venv", "Scripts", "python.exe")
FRONT = "http://localhost:5173"
TAG = "SMOKE105"
# Casilla real con plus-addressing: el email llega de verdad y se puede mirar.
RECEPTOR = "ulisessbaretta+smoke105@gmail.com"
LOGO = f"{settings.FRONTEND_PUBLIC_URL.rstrip('/')}/friese-mark.png"


def resend_get(path):
    req = urllib.request.Request(
        f"https://api.resend.com{path}",
        headers={"Authorization": f"Bearer {settings.RESEND_API_KEY}",
                 "User-Agent": "friese-smoke105/1.0", "Accept": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read().decode())


def tiene_marca(html):
    """¿Este email trae la cabecera de marca? Las tres piezas juntas."""
    return ("#1a1a22" in html.lower()  # la banda oscura de la marca
            and "#d6ac31" in html.lower()  # el dorado del logo
            and LOGO in html  # el isotipo
            and 'alt="Friese"' in html)  # y el nombre si la imagen no carga


procesos = [
    subprocess.Popen([PYTHON, "manage.py", "runserver", "127.0.0.1:8000", "--noreload"],
                     cwd=BASE_DIR, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL),
    subprocess.Popen(["npm.cmd", "run", "dev"], cwd=os.path.join(BASE_DIR, "frontend"),
                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL),
]

nav = None
company = None
remito = None
usuarios = []
try:
    for url in ("http://127.0.0.1:8000/admin/login/", FRONT):
        limite = time.time() + 120
        while time.time() < limite:
            try:
                requests.get(url, timeout=5)
                break
            except Exception:
                time.sleep(0.5)
        else:
            raise RuntimeError(f"no levantó {url}")

    # --- Datos de prueba ---------------------------------------------------
    company = Company.objects.create(name=f"Cerealera {TAG} SA",
                                     email=f"{TAG.lower()}@friese.test")
    op_pass = secrets.token_urlsafe(18)
    operador = User.objects.create_user(
        username=f"{TAG.lower()}_op", password=op_pass, company=company,
        role=User.OPERATOR, email=f"{TAG.lower()}op@friese.test")
    usuarios.append(operador)
    remito = Shipment.objects.create(
        company=company, operator=operador, receiver_name=f"Corralón {TAG}",
        receiver_email=RECEPTOR, status=Shipment.DISPATCHED,
        dispatched_at=timezone.now(), public_token=uuid.uuid4(),
        response_deadline=timezone.now() + timedelta(hours=48))

    # --- 1. El favicon -----------------------------------------------------
    print("=== 1. El favicon de la pestaña ===")
    nav = Browser()
    nav.goto(f"{FRONT}/login")
    nav.wait("document.querySelector('#username')", label="login")
    icono = nav.js("(document.querySelector('link[rel=icon]') || {}).href || ''")
    check(icono.endswith("/friese-mark.png"),
          "CRITERIO — la pestaña usa el isotipo de Friese, no el de Vite", icono)
    check("vite" not in icono.lower(), "y no quedó ningún resto del favicon de Vite")
    r = requests.get(icono, timeout=30)
    check(r.status_code == 200 and r.content[:8] == b"\x89PNG\r\n\x1a\n",
          "y el archivo existe de verdad (es un PNG que se sirve)",
          f"HTTP {r.status_code}, {len(r.content)} bytes")
    check(nav.js("!!document.querySelector('link[rel=\"apple-touch-icon\"]')"),
          "con su versión para la pantalla de inicio del celular")

    # --- 2. El título de cada pantalla -------------------------------------
    print("\n=== 2. El título de la pestaña, pantalla por pantalla ===")
    esperados = [
        ("/login", "document.querySelector('#username')", "Ingresar · Friese"),
        ("/recuperar-contrasena", "document.querySelector('form')",
         "Recuperar contraseña · Friese"),
        ("/restablecer/abc/def", "document.body.innerText.length > 40",
         "Elegir una contraseña nueva · Friese"),
        (f"/remito/{remito.public_token}", "document.body.innerText.includes('Productos')",
         f"Remito #{remito.pk} · Friese"),
        ("/una-ruta-que-no-existe", "document.querySelector('[data-testid=notfound-message]')",
         "Página no encontrada · Friese"),
    ]
    for ruta, espera, titulo in esperados:
        nav.goto(f"{FRONT}{ruta}")
        nav.wait(espera, label=ruta)
        nav.wait(f"document.title === {titulo!r}", timeout=10, label=f"título de {ruta}")
        check(nav.js("document.title") == titulo, f"«{ruta}» muestra «{titulo}»",
              nav.js("document.title"))

    # Las tres pantallas del operador necesitan sesión.
    nav.goto(f"{FRONT}/login")
    nav.wait("document.querySelector('#username')", label="login")
    nav.fill("#username", f"{TAG.lower()}_op")
    nav.fill("#password", op_pass)
    nav.click("button[type=submit]")
    nav.wait("location.pathname === '/'", timeout=60, label="entra a la lista")
    for ruta, espera, titulo in [
        ("/", "document.querySelector('h1')", "Remitos · Friese"),
        ("/remitos/nuevo", "document.querySelector('#receiver-name')", "Nuevo remito · Friese"),
        (f"/remitos/{remito.pk}", "document.querySelector('h1')",
         f"Remito #{remito.pk} · Friese"),
    ]:
        nav.goto(f"{FRONT}{ruta}")
        nav.wait(espera, label=ruta)
        nav.wait(f"document.title === {titulo!r}", timeout=10, label=f"título de {ruta}")
        check(nav.js("document.title") == titulo, f"«{ruta}» muestra «{titulo}»",
              nav.js("document.title"))

    check(nav.js("document.title").endswith("· Friese"),
          "CRITERIO — la marca queda siempre al final del título")
    nav.shot("m01-titulo-pestana")

    # --- 3. Los emails, armados con las funciones reales -------------------
    print("\n=== 3. La marca en los cinco emails ===")
    link = build_public_link(remito)
    cuerpos = {
        "despacho (5.1)": _dispatch_email_content(remito, link)[1],
        "recordatorio (5.2)": _reminder_email_content(remito, link, 24)[1],
        "queja al admin (5.3)": _dispute_email_content(remito, [], timezone.now())[1],
        "cierre automático (5.4)": _auto_close_email_content(remito, link)[1],
        "recuperación de contraseña (7.4)": _reset_email_content(
            operador, "https://app.friese.com.ar/restablecer/a/b", 24, None)[1],
    }
    for nombre, html in cuerpos.items():
        check(tiene_marca(html),
              f"CRITERIO — el email de {nombre} lleva la cabecera de marca")
    check(all("Friese — trazabilidad" in html for html in cuerpos.values()),
          "y los cinco conservan la firma del pie")
    check(all("#4F46E5" in html or "#4f46e5" in html
              for nombre, html in cuerpos.items() if "queja" not in nombre),
          "con el indigo funcional del spec en los botones")

    # --- 4. Un email REAL, leído de vuelta desde Resend --------------------
    print("\n=== 4. El email que salió de verdad ===")
    check(send_dispatch_email(remito), "el email de despacho se envía", RECEPTOR)
    asunto = f"Remito #{remito.pk} de {company.name}"
    enviado, limite = None, time.time() + 60
    while time.time() < limite and not enviado:
        enviado = next((e for e in resend_get("/emails").get("data", [])
                        if asunto in (e.get("subject") or "")), None)
        if not enviado:
            time.sleep(3)
    check(enviado is not None, "y aparece en la API de Resend", asunto)
    detalle = resend_get(f"/emails/{enviado['id']}")
    html = detalle.get("html") or ""
    check(tiene_marca(html),
          "CRITERIO — el HTML que SALIÓ trae el isotipo, el dorado y el nombre")
    check(RECEPTOR in (detalle.get("to") or []), "y fue a la casilla del receptor",
          str(detalle.get("to")))
    check(link in html, "con el link único del remito adentro")
    print(f"    id en Resend: {enviado['id']} | estado: {enviado.get('last_event')}")

    # El logo del email tiene que existir donde dice que existe.
    r = requests.get(f"{FRONT}/friese-mark.png", timeout=30)
    check(r.status_code == 200 and r.content[:8] == b"\x89PNG\r\n\x1a\n",
          "y el isotipo que referencia el email se sirve desde el frontend",
          f"HTTP {r.status_code}")
finally:
    ids_remitos = [remito.pk] if remito else []
    ids_usuarios = [u.pk for u in usuarios if u]
    Shipment.objects.filter(pk__in=ids_remitos).delete()
    User.objects.filter(pk__in=ids_usuarios).delete()
    ids_empresas = [company.pk] if company else []
    Company.objects.filter(pk__in=ids_empresas).delete()
    borradas = borrar_historial(empresas=ids_empresas, usuarios=ids_usuarios,
                                remitos=ids_remitos)

    if nav:
        nav.close()
    for proceso in procesos:
        proceso.terminate()
        try:
            proceso.wait(timeout=10)
        except Exception:
            proceso.kill()

print(f"\n  limpieza: {borradas} filas de historial borradas; quedan "
      f"{Company.objects.filter(name__contains=TAG).count()} empresas con la marca {TAG}")
sys.exit(summary("marca en pestaña y emails (10.5)"))
