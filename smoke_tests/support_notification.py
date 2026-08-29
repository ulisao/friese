"""Criterio de aceptación de la 9.2 — el aviso por email al abrirse un ticket.

Una empresa abre un ticket desde el panel y a Friese le llega el email, con la
empresa, el asunto y un link que abre ESA ficha en el Django Admin. Se prueba de
punta a punta: el alta va por el formulario REAL del admin (el único camino por el
que nace un ticket) y el email se verifica contra la API de Resend, o sea el que
salió de verdad — no un mock.

    python smoke_tests/support_notification.py

Levanta su propio server local contra la base de siempre, crea sus datos con la
marca SMOKE92 y los borra al final, historial incluido. El email SÍ se manda de
verdad a SUPPORT_NOTIFICATION_EMAIL: es justamente lo que se está probando.
"""

import json
import os
import re
import secrets
import subprocess
import sys
import time
import urllib.request

import django
import requests

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE_DIR)
sys.path.insert(0, HERE)
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
django.setup()

from django.conf import settings  # noqa: E402

from companies.models import Company, UsageLog  # noqa: E402
from support.emails import support_recipients  # noqa: E402
from support.models import SupportTicket  # noqa: E402
from users.groups import ensure_company_admin_group  # noqa: E402
from users.models import User  # noqa: E402

from e2e import borrar_historial, check, summary  # noqa: E402

PYTHON = os.path.join(BASE_DIR, "venv", "Scripts", "python.exe")
PUERTO = 8027
LOCAL = f"http://127.0.0.1:{PUERTO}"
ADMIN = f"{LOCAL}/admin"
TICKETS = "/support/supportticket"
TAG = "SMOKE92"


def resend(path):
    """GET a la API de Resend (la misma que usa el smoke del aviso de queja, 5.3)."""
    req = urllib.request.Request(
        f"https://api.resend.com{path}",
        headers={"Authorization": f"Bearer {settings.RESEND_API_KEY}",
                 "User-Agent": "friese-smoke92/1.0", "Accept": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read().decode())


def esperar_email(marca, timeout=90):
    """El email con `marca` en el asunto, ya entregado a Resend. None si no llega.

    Resend tarda unos segundos en listarlo, así que se reintenta en vez de mirar
    una sola vez y dar un falso negativo.
    """
    limite = time.time() + timeout
    while time.time() < limite:
        for email in resend("/emails").get("data", []):
            if marca in (email.get("subject") or ""):
                return resend(f"/emails/{email['id']}")
        time.sleep(3)
    return None


def entrar_al_admin(usuario, password):
    s = requests.Session()
    s.get(f"{ADMIN}/login/", timeout=30).raise_for_status()
    r = s.post(f"{ADMIN}/login/",
               data={"username": usuario, "password": password,
                     "csrfmiddlewaretoken": s.cookies["csrftoken"], "next": "/admin/"},
               headers={"Referer": f"{ADMIN}/login/"},
               allow_redirects=False, timeout=30)
    return s, r


def guardar(sesion, path, datos):
    url = f"{ADMIN}{path}"
    sesion.get(url, timeout=30).raise_for_status()
    datos = dict(datos)
    datos["csrfmiddlewaretoken"] = sesion.cookies["csrftoken"]
    datos["_save"] = "Grabar"
    r = sesion.post(url, data=datos, headers={"Referer": url},
                    allow_redirects=False, timeout=60)
    if r.status_code == 200:
        errores = re.findall(r'<ul class="errorlist[^"]*"[^>]*>(.*?)</ul>', r.text, re.S)
        if errores:
            print("    errores del formulario:", " | ".join(
                re.sub(r"<[^>]+>", " ", e).strip() for e in errores)[:400])
    return r


servidor = subprocess.Popen(
    [PYTHON, "manage.py", "runserver", f"127.0.0.1:{PUERTO}", "--noreload"],
    cwd=BASE_DIR, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

empresas = []
usuarios = []
tickets = []
borradas = 0
try:
    limite = time.time() + 90
    while time.time() < limite:
        try:
            requests.get(f"{ADMIN}/login/", timeout=5)
            break
        except Exception:
            time.sleep(0.4)
    else:
        raise RuntimeError("no levantó el backend")

    # --- 0. Configuración --------------------------------------------------
    print("\n=== 0. La casilla de aviso está configurada ===")
    destinatarios = support_recipients()
    check(bool(destinatarios), "SUPPORT_NOTIFICATION_EMAIL tiene destinatario",
          f"{len(destinatarios)} casilla(s)")
    check(bool(settings.RESEND_API_KEY), "RESEND_API_KEY cargada")
    if not destinatarios or not settings.RESEND_API_KEY:
        raise RuntimeError("sin casilla o sin API key no hay nada que probar")

    # --- Datos de prueba ---------------------------------------------------
    pass_super = secrets.token_urlsafe(18)
    superadmin = User.objects.create_superuser(
        username=f"{TAG.lower()}_root", password=pass_super,
        email=f"{TAG.lower()}root@friese.test")
    usuarios.append(superadmin)

    empresa = Company.objects.create(name=f"Transportes {TAG} SA",
                                     email=f"{TAG.lower()}@friese.test")
    empresas.append(empresa)

    pass_admin = secrets.token_urlsafe(18)
    admin_empresa = User.objects.create_user(
        username=f"{TAG.lower()}_admin", password=pass_admin, company=empresa,
        role=User.ADMIN, is_staff=True, email=f"{TAG.lower()}admin@friese.test")
    admin_empresa.groups.add(ensure_company_admin_group())
    usuarios.append(admin_empresa)

    mes = time.strftime("%Y-%m")
    emails_antes = (UsageLog.objects.filter(company=empresa, month=mes)
                    .values_list("emails_sent", flat=True).first() or 0)

    sesion, r = entrar_al_admin(f"{TAG.lower()}_admin", pass_admin)
    check(r.status_code == 302, "el admin de la empresa entra al panel",
          f"HTTP {r.status_code}")

    # --- 1. Abre el ticket -------------------------------------------------
    print("\n=== 1. La empresa abre un ticket desde el panel ===")
    asunto = f"La camara no abre en el celular {TAG}"
    descripcion = ("El operador Juan no puede sacar la foto de despacho desde su "
                   "telefono: la pantalla queda en negro.")
    r = guardar(sesion, f"{TICKETS}/add/", {"subject": asunto,
                                            "description": descripcion})
    check(r.status_code == 302, "el alta guarda", f"HTTP {r.status_code}")

    ticket = SupportTicket.objects.filter(subject=asunto).first()
    check(ticket is not None, "el ticket quedó creado")
    if ticket is None:
        raise RuntimeError("no se creó el ticket: no hay nada que verificar")
    tickets.append(ticket)

    # --- 2. El email salió -------------------------------------------------
    print("\n=== 2. CRITERIO: a Friese le llega el aviso ===")
    # Se busca por el NÚMERO del ticket, no por la marca: los avisos de las corridas
    # anteriores de este test siguen listados en Resend y también dicen SMOKE92.
    detalle = esperar_email(f"Ticket #{ticket.pk} de")
    check(detalle is not None,
          "CRITERIO: el alta disparó un email y Resend lo aceptó")
    if detalle is None:
        raise RuntimeError("no llegó el email: mirar el log del server")

    check(sorted(detalle.get("to") or []) == sorted(destinatarios),
          "va a SUPPORT_NOTIFICATION_EMAIL", detalle.get("to"))
    check((detalle.get("last_event") or "") not in ("bounced", "failed"),
          "y Resend no lo rechazó", detalle.get("last_event"))

    html = detalle.get("html") or ""
    texto = detalle.get("text") or ""
    check(empresa.name in (detalle.get("subject") or "") and empresa.name in html,
          "el email dice de qué EMPRESA es", detalle.get("subject"))
    check(asunto in (detalle.get("subject") or "") and asunto in html,
          "y trae el ASUNTO del ticket")
    check(descripcion in html and descripcion in texto,
          "además del texto que escribió el cliente")
    check(admin_empresa.get_username() in html, "y quién lo abrió")
    check((detalle.get("reply_to") or []) == [admin_empresa.email],
          "responder el email le contesta a quien abrió el ticket",
          detalle.get("reply_to"))

    # --- 3. El link ---------------------------------------------------------
    print("\n=== 3. CRITERIO: el link abre ESE ticket en el panel ===")
    esperado = f"{LOCAL}/admin{TICKETS}/{ticket.pk}/change/"
    check(esperado in html and esperado in texto,
          "el email trae el link directo a la ficha del ticket", esperado)

    sesion_root, _ = entrar_al_admin(f"{TAG.lower()}_root", pass_super)
    r = sesion_root.get(esperado, timeout=30)
    check(r.status_code == 200, "CRITERIO: el link abre (HTTP 200) para Friese",
          f"HTTP {r.status_code}")
    check(asunto in r.text and empresa.name in r.text,
          "y lo que abre es la ficha de ESE ticket, con su empresa")
    check('name="status"' in r.text,
          "desde donde Friese le mueve el estado (9.1)")

    # --- 4. Lo que NO tiene que pasar ---------------------------------------
    print("\n=== 4. El aviso es del ALTA, y no lo paga la empresa ===")
    emails_despues = (UsageLog.objects.filter(company=empresa, month=mes)
                      .values_list("emails_sent", flat=True).first() or 0)
    check(emails_despues == emails_antes,
          "no se cuenta contra el cupo de emails de la empresa: es un aviso interno",
          f"{emails_antes} -> {emails_despues}")

    r = guardar(sesion, f"{TICKETS}/{ticket.pk}/change/", {
        "subject": asunto,
        "description": descripcion + "\n\nAmpliacion: pasa con Android nada mas."})
    check(r.status_code == 302, "la empresa amplía su ticket", f"HTTP {r.status_code}")

    ticket.refresh_from_db()
    r = guardar(sesion_root, f"{TICKETS}/{ticket.pk}/change/", {
        "company": empresa.pk, "subject": asunto, "description": ticket.description,
        "status": SupportTicket.IN_PROGRESS})
    check(r.status_code == 302, "y Friese lo pasa a «En curso»",
          f"HTTP {r.status_code}")

    time.sleep(10)
    # Se cuentan los avisos DE ESTE ticket, no todos los que llevan la marca: el
    # listado de Resend conserva los de las corridas anteriores de este mismo test
    # (que también dicen SMOKE92) y con esos adentro el conteo nunca daba 1.
    de_este_ticket = [e for e in resend("/emails").get("data", [])
                      if f"Ticket #{ticket.pk} de" in (e.get("subject") or "")]
    check(len(de_este_ticket) == 1,
          "editar el ticket NO vuelve a avisar: el aviso es del alta",
          f"{len(de_este_ticket)} email(s) de este ticket")

    print("\n  destinatarios:", detalle.get("to"), "| asunto:", detalle.get("subject"))
    print("  link enviado:", esperado)
finally:
    ids_tickets = [t.pk for t in tickets if t]
    ids_usuarios = [u.pk for u in usuarios if u]
    ids_empresas = [c.pk for c in empresas if c]
    # Los tickets primero: `created_by` es PROTECT.
    SupportTicket.objects.filter(pk__in=ids_tickets).delete()
    UsageLog.objects.filter(company_id__in=ids_empresas).delete()
    User.objects.filter(pk__in=ids_usuarios).delete()
    Company.objects.filter(pk__in=ids_empresas).delete()
    borradas = borrar_historial(empresas=ids_empresas, usuarios=ids_usuarios)
    borradas += SupportTicket.history.filter(id__in=ids_tickets).delete()[0]

    servidor.terminate()
    try:
        servidor.wait(timeout=10)
    except Exception:
        servidor.kill()

print(f"\n  limpieza: {borradas} filas de historial borradas; quedan "
      f"{SupportTicket.objects.filter(subject__contains=TAG).count()} tickets con la "
      f"marca {TAG}")
sys.exit(summary("aviso de ticket nuevo (9.2)"))
