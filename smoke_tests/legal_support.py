"""Criterio de aceptación de las tareas 7.5, 7.6 y 7.7.

- 7.5: los Términos y la Política de Privacidad existen, son públicos, dicen que son un
  borrador pendiente de revisión legal, y se llegan desde el panel de administración.
- 7.6: el receptor ve el aviso de qué pasa con su foto ANTES de responder o de abrir la
  cámara, sin un muro de texto que le tape la acción.
- 7.7: el contacto de soporte aparece en los cuatro puntos de fricción: las dos
  pantallas de error del backend, la de 404 del frontend, el pie del panel y el pie de
  los emails.

    python smoke_tests/legal_support.py

El backend se levanta con DEBUG=False (sigue en ambiente `development`, así que no
fuerza HTTPS): sin eso las pantallas de error son las de debug de Django. El frontend
es el Vite de siempre en :5173. Crea sus datos con la marca SMOKE77 y los borra al
final, historial incluido (8.2).
"""

import os
import re
import secrets
import subprocess
import sys
import time
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
from django.test import RequestFactory  # noqa: E402
from django.utils import timezone  # noqa: E402

from companies.models import Company  # noqa: E402
from config.errors import server_error  # noqa: E402
from shipments.emails import (  # noqa: E402
    _auto_close_email_content,
    _dispatch_email_content,
    _dispute_email_content,
    _reminder_email_content,
    build_public_link,
)
from shipments.models import Shipment  # noqa: E402
from support.emails import _new_ticket_email_content  # noqa: E402
from support.models import SupportTicket  # noqa: E402
from users.emails import _reset_email_content  # noqa: E402
from users.models import User  # noqa: E402

from browser import Browser  # noqa: E402
from e2e import borrar_historial, check, summary  # noqa: E402

PYTHON = os.path.join(BASE_DIR, "venv", "Scripts", "python.exe")
PUERTO = 8000  # el que proxea el Vite: la pantalla del receptor consume la API
LOCAL = f"http://127.0.0.1:{PUERTO}"
ADMIN = f"{LOCAL}/admin"
FRONT = "http://localhost:5173"
TAG = "SMOKE77"
EMAIL = settings.SUPPORT_CONTACT_EMAIL
WPP = settings.SUPPORT_WHATSAPP_URL

entorno = {**os.environ, "DEBUG": "False"}
procesos = [
    subprocess.Popen([PYTHON, "manage.py", "runserver", f"127.0.0.1:{PUERTO}", "--noreload"],
                     cwd=BASE_DIR, env=entorno,
                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL),
    subprocess.Popen(["npm.cmd", "run", "dev"], cwd=os.path.join(BASE_DIR, "frontend"),
                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL),
]

nav = None
company = None
remito = None
usuarios = []
tickets = []
try:
    for url in (f"{ADMIN}/login/", FRONT):
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
    company = Company.objects.create(name=f"Corralón {TAG} SA",
                                     email=f"{TAG.lower()}@friese.test")
    pass_root = secrets.token_urlsafe(18)
    superadmin = User.objects.create_superuser(
        username=f"{TAG.lower()}_root", password=pass_root,
        email=f"{TAG.lower()}root@friese.test")
    operador = User.objects.create_user(
        username=f"{TAG.lower()}_op", password=secrets.token_urlsafe(18),
        company=company, role=User.OPERATOR, email=f"{TAG.lower()}op@friese.test")
    usuarios += [superadmin, operador]
    # Despachado y sin responder: es el estado en el que el receptor ve los botones.
    remito = Shipment.objects.create(
        company=company, operator=operador, receiver_name=f"Obra {TAG}",
        status=Shipment.DISPATCHED, dispatched_at=timezone.now(),
        public_token=uuid.uuid4(),
        response_deadline=timezone.now() + timedelta(hours=48))

    # --- 1. Los documentos legales (7.5) -----------------------------------
    print("=== 1. Términos y Privacidad (7.5) ===")
    nav = Browser()
    for ruta, titulo in (("/terminos", "Términos de Servicio"),
                         ("/privacidad", "Política de Privacidad")):
        nav.goto(f"{FRONT}{ruta}")
        nav.wait("document.querySelector('[data-testid=legal-draft-notice]')", label=ruta)
        texto = nav.text("body")
        check(titulo in texto, f"«{ruta}» abre sin login y es «{titulo}»",
              texto.splitlines()[0][:50])
        aviso = nav.text("[data-testid=legal-draft-notice]")
        check("pendiente de revisión legal" in aviso and "borrador" in aviso.lower(),
              "CRITERIO — con el aviso visible de versión preliminar", aviso[:60])
        check("v1-borrador" in texto, "y la versión del documento a la vista")
        check(EMAIL in texto, "con el contacto de soporte (7.7)")
    nav.shot("l01-terminos")

    texto = nav.text("body")
    check("Qué datos se registran" in texto or "Qué datos" in texto,
          "la política dice qué datos se registran")
    check("Cuánto tiempo se conservan" in texto, "y por cuánto tiempo se conservan")
    check("Dónde se guardan" in texto, "y quién más los procesa")
    nav.shot("l02-privacidad")

    # Se llegan de una a la otra sin volver al inicio.
    nav.click_js(
        "Array.from(document.querySelectorAll('a')).find("
        "(a) => a.getAttribute('href') === '/terminos')", label="link cruzado")
    nav.wait("location.pathname === '/terminos'", label="ida a términos")
    check(True, "y cada documento linkea al otro")

    # --- 2. El aviso al receptor (7.6) -------------------------------------
    print("\n=== 2. El consentimiento del receptor (7.6) ===")
    nav.goto(f"{FRONT}/remito/{remito.public_token}")
    nav.wait("document.querySelector('[data-testid=privacy-notice]')", label="pantalla del receptor")
    aviso = nav.text("[data-testid=privacy-notice]")
    check("fotos" in aviso and "evidencia de esta entrega" in aviso,
          "CRITERIO — el aviso explica qué pasa con la foto y los datos", aviso[:80])
    check(nav.js(
        "!!document.querySelector('[data-testid=privacy-notice] a[href=\"/privacidad\"]')"),
        "y linkea a la Política de Privacidad")
    # "Visible ANTES de usar la cámara": el aviso está en el DOM y arriba de los dos
    # botones, que son la única puerta a la cámara y a la respuesta.
    check(nav.js("""(() => {
        const aviso = document.querySelector('[data-testid=privacy-notice]');
        const boton = document.querySelector('[data-testid=accept]');
        return !!aviso && !!boton &&
          (aviso.compareDocumentPosition(boton) & Node.DOCUMENT_POSITION_FOLLOWING) > 0;
    })()"""), "CRITERIO — y está ARRIBA de los botones, antes de cualquier acción")
    check(not nav.js("!!document.querySelector('[role=dialog]')"),
          "sin modal que tape la pantalla: es un párrafo, no un muro legal")
    nav.shot("l03-aviso-receptor")

    # --- 3. El soporte en las pantallas de error (7.7) ---------------------
    print("\n=== 3. El contacto en los puntos de fricción (7.7) ===")
    html404 = requests.get(f"{LOCAL}/ruta-que-no-existe/", timeout=30).text
    check(EMAIL in html404 and WPP in html404,
          "el 404 del backend ofrece los dos canales", EMAIL)
    html500 = server_error(RequestFactory().get("/x/")).content.decode()
    check(EMAIL in html500 and WPP in html500, "el 500 del backend también")

    nav.goto(f"{FRONT}/una-ruta-que-no-existe")
    nav.wait("document.querySelector('[data-testid=notfound-message]')", label="404 del frontend")
    texto = nav.text("body")
    check(EMAIL in texto and nav.js(
        f"!!Array.from(document.querySelectorAll('a')).find((a) => a.href === '{WPP}')"),
        "el 404 del frontend, los mismos dos canales")

    # --- 4. El pie del panel (7.5 + 7.7) -----------------------------------
    print("\n=== 4. El pie del panel de administración ===")
    login = requests.get(f"{ADMIN}/login/", timeout=30).text
    check(EMAIL in login and WPP in login,
          "el contacto está hasta en el login del panel, que es donde uno se traba")
    check("/terminos" in login and "/privacidad" in login,
          "CRITERIO 7.5 — y los dos documentos se llegan desde el panel")

    sesion = requests.Session()
    sesion.get(f"{ADMIN}/login/", timeout=30)
    sesion.post(f"{ADMIN}/login/",
                data={"username": f"{TAG.lower()}_root", "password": pass_root,
                      "csrfmiddlewaretoken": sesion.cookies["csrftoken"], "next": "/admin/"},
                headers={"Referer": f"{ADMIN}/login/"}, timeout=30)
    indice = sesion.get(f"{ADMIN}/", timeout=30).text
    check(EMAIL in indice and "/terminos" in indice,
          "y adentro del panel también, en todas las pantallas")
    esperado = f"{settings.FRONTEND_PUBLIC_URL.rstrip('/')}/terminos"
    check(esperado in indice, "los links apuntan a la app, no a una ruta del backend",
          esperado)

    # --- 5. El pie de los emails (7.7) -------------------------------------
    print("\n=== 5. El pie de los emails ===")
    link = build_public_link(remito)
    ticket = SupportTicket.objects.create(
        company=company, created_by=operador, subject=f"Prueba {TAG}",
        description="Texto de prueba.")
    tickets.append(ticket)
    cuerpos = {
        "despacho (5.1)": _dispatch_email_content(remito, link),
        "recordatorio (5.2)": _reminder_email_content(remito, link, 24),
        "queja al admin (5.3)": _dispute_email_content(remito, [], timezone.now()),
        "cierre automático (5.4)": _auto_close_email_content(remito, link),
        "recuperación de contraseña (7.4)": _reset_email_content(
            operador, "https://app.friese.com.ar/restablecer/a/b", 24, None),
    }
    for nombre, (_, html, texto) in cuerpos.items():
        check(EMAIL in html and WPP in html and f"mailto:{EMAIL}" in html,
              f"CRITERIO — el email de {nombre} lleva el contacto en el pie")
        check(EMAIL in texto, f"y también su versión en texto plano ({nombre})")

    _, html_ticket, _ = _new_ticket_email_content(ticket, f"{ADMIN}/x/")
    check(f"mailto:{EMAIL}" not in html_ticket,
          "el aviso interno de ticket NO se invita a sí mismo a escribirse")

    # --- 6. Coherencia con la landing --------------------------------------
    print("\n=== 6. El mismo contacto en todos lados ===")
    check(EMAIL == "contacto@friese.com.ar" and "5493472430136" in WPP,
          "el contacto del producto es el MISMO que publica la landing",
          f"{EMAIL} / {WPP}")
    check(not [e for e in nav.errores_de_consola() if "404" not in e],
          "ninguna pantalla dejó errores de consola inesperados")
finally:
    ids_remitos = [remito.pk] if remito else []
    ids_usuarios = [u.pk for u in usuarios if u]
    ids_empresas = [company.pk] if company else []
    SupportTicket.objects.filter(pk__in=[t.pk for t in tickets if t]).delete()
    Shipment.objects.filter(pk__in=ids_remitos).delete()
    User.objects.filter(pk__in=ids_usuarios).delete()
    Company.objects.filter(pk__in=ids_empresas).delete()
    borradas = borrar_historial(empresas=ids_empresas, usuarios=ids_usuarios,
                                remitos=ids_remitos)
    borradas += SupportTicket.history.filter(id__in=[t.pk for t in tickets if t]).delete()[0]

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
sys.exit(summary("legales, consentimiento y soporte (7.5 / 7.6 / 7.7)"))
