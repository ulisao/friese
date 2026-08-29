"""Criterio de aceptación de la 9.1 — tickets de soporte en el Django Admin.

Un admin de empresa abre su ticket desde SU panel y no puede ver ni tocar los de otra
empresa, ni mover el estado del suyo (eso lo hace Friese al resolverlo). Se prueba
contra los formularios REALES del admin por HTTP, que es el único camino por el que se
crean los tickets: no hay endpoint de API ni pantalla en el frontend.

    python smoke_tests/support_tickets.py

Levanta su propio server local contra la base de siempre, crea sus datos con la marca
SMOKE91 —dos empresas, para probar el aislamiento igual que en la 4.1— y los borra al
final, incluidas las filas de historial que generó (8.2).
"""

import os
import re
import secrets
import subprocess
import sys
import time

import django
import requests

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE_DIR)
sys.path.insert(0, HERE)
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
django.setup()

from companies.models import Company  # noqa: E402
from support.models import SupportTicket  # noqa: E402
from users.groups import ensure_company_admin_group  # noqa: E402
from users.models import User  # noqa: E402

from browser import Browser  # noqa: E402
from e2e import borrar_historial, check, summary  # noqa: E402

PYTHON = os.path.join(BASE_DIR, "venv", "Scripts", "python.exe")
PUERTO = 8026
LOCAL = f"http://127.0.0.1:{PUERTO}"
ADMIN = f"{LOCAL}/admin"
TICKETS = "/support/supportticket"
TAG = "SMOKE91"


def entrar_al_admin(usuario, password):
    """Sesión con el login del Django Admin ya hecho."""
    s = requests.Session()
    s.get(f"{ADMIN}/login/", timeout=30).raise_for_status()
    r = s.post(f"{ADMIN}/login/",
               data={"username": usuario, "password": password,
                     "csrfmiddlewaretoken": s.cookies["csrftoken"], "next": "/admin/"},
               headers={"Referer": f"{ADMIN}/login/"},
               allow_redirects=False, timeout=30)
    return s, r


def pantalla(sesion, path):
    """HTML de una pantalla del admin y los names de sus inputs.

    Los names distinguen un campo EDITABLE (tiene input) de uno que el admin dibuja
    de solo lectura (se ve el valor, no el input).
    """
    r = sesion.get(f"{ADMIN}{path}", timeout=30)
    r.raise_for_status()
    nombres = set(re.findall(r'<(?:input|select|textarea)[^>]*\bname="([^"]+)"', r.text))
    return r.text, nombres


def guardar(sesion, path, datos):
    """Envía el formulario del admin con `datos`. Devuelve la respuesta.

    El form del ticket es plano (no tiene inlines), así que se mandan los campos
    explícitos: es todo lo que un navegador enviaría.
    """
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

nav = None
empresas = []
usuarios = []
tickets = []
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

    # --- Datos de prueba: dos empresas con su admin, más el superadmin ----
    pass_super = secrets.token_urlsafe(18)
    superadmin = User.objects.create_superuser(
        username=f"{TAG.lower()}_root", password=pass_super,
        email=f"{TAG.lower()}root@friese.test")
    usuarios.append(superadmin)

    empresa_a = Company.objects.create(name=f"Fletes {TAG} A SA",
                                       email=f"{TAG.lower()}a@friese.test")
    empresa_b = Company.objects.create(name=f"Fletes {TAG} B SRL",
                                       email=f"{TAG.lower()}b@friese.test")
    empresas += [empresa_a, empresa_b]

    grupo = ensure_company_admin_group()
    pass_a, pass_b = secrets.token_urlsafe(18), secrets.token_urlsafe(18)
    admin_a = User.objects.create_user(
        username=f"{TAG.lower()}_admin_a", password=pass_a, company=empresa_a,
        role=User.ADMIN, is_staff=True, email=f"{TAG.lower()}aa@friese.test")
    admin_b = User.objects.create_user(
        username=f"{TAG.lower()}_admin_b", password=pass_b, company=empresa_b,
        role=User.ADMIN, is_staff=True, email=f"{TAG.lower()}bb@friese.test")
    for u in (admin_a, admin_b):
        u.groups.add(grupo)
    usuarios += [admin_a, admin_b]

    sesion_root, r = entrar_al_admin(f"{TAG.lower()}_root", pass_super)
    check(r.status_code == 302, "el superadmin entra al panel", f"HTTP {r.status_code}")
    sesion_a, r = entrar_al_admin(f"{TAG.lower()}_admin_a", pass_a)
    check(r.status_code == 302, "el admin de la empresa A entra al panel",
          f"HTTP {r.status_code}")
    sesion_b, _ = entrar_al_admin(f"{TAG.lower()}_admin_b", pass_b)

    # --- 1. El modelo ------------------------------------------------------
    print("\n=== 1. El modelo SupportTicket ===")
    campos = {f.name: f for f in SupportTicket._meta.get_fields() if hasattr(f, "attname")}
    check({"company", "created_by", "subject", "description", "status",
           "created_at", "updated_at"} <= set(campos),
          "tiene los campos que pide la tarea", sorted(campos))
    check([c[0] for c in campos["status"].choices]
          == ["open", "in_progress", "resolved", "closed"],
          "los cuatro estados, en orden", [c[0] for c in campos["status"].choices])
    check(campos["status"].default == SupportTicket.OPEN,
          "y arranca en 'open' por default", campos["status"].default)
    check(campos["created_at"].auto_now_add and campos["updated_at"].auto_now,
          "las dos fechas las sella el servidor, no el formulario")

    # --- 2. El admin de empresa abre su ticket -----------------------------
    print("\n=== 2. El admin de la empresa A abre un ticket desde su panel ===")
    html, nombres = pantalla(sesion_a, f"{TICKETS}/add/")
    check({"subject", "description"} <= nombres,
          "el formulario de alta le pide el asunto y la descripción", sorted(nombres))
    check(not ({"status", "company", "created_by"} & nombres),
          "y NO le ofrece elegir estado, empresa ni autor",
          sorted({"status", "company", "created_by"} & nombres))

    r = guardar(sesion_a, f"{TICKETS}/add/", {
        "subject": f"No me llega el email de despacho {TAG}",
        "description": "Despache tres remitos y el receptor dice que no le llego nada.",
        # Los manda a mano, como si editara el HTML: tienen que ignorarse.
        "status": SupportTicket.RESOLVED,
        "company": empresa_b.pk,
        "created_by": superadmin.pk,
    })
    check(r.status_code == 302, "el alta guarda", f"HTTP {r.status_code}")

    ticket_a = SupportTicket.objects.filter(subject__contains=TAG).first()
    check(ticket_a is not None, "el ticket quedó creado")
    tickets.append(ticket_a)
    check(ticket_a.status == SupportTicket.OPEN,
          "CRITERIO: queda en 'open' aunque haya mandado otro estado", ticket_a.status)
    check(ticket_a.company_id == empresa_a.pk,
          "queda en SU empresa, no en la que mandó en el POST", str(ticket_a.company))
    check(ticket_a.created_by_id == admin_a.pk,
          "y a nombre de quien lo abrió", str(ticket_a.created_by))

    # --- 3. No puede mover el estado ---------------------------------------
    print("\n=== 3. El estado lo mueve Friese, no el cliente ===")
    html, nombres = pantalla(sesion_a, f"{TICKETS}/{ticket_a.pk}/change/")
    check("status" not in nombres,
          "CRITERIO: en su propio ticket el estado le llega de solo lectura, sin input")
    check("Abierto" in html and "Estado" in html, "pero lo VE en la ficha")
    check(not ({"company", "created_by"} & nombres),
          "la empresa y el autor tampoco son editables")

    r = guardar(sesion_a, f"{TICKETS}/{ticket_a.pk}/change/", {
        "subject": ticket_a.subject, "description": ticket_a.description,
        "status": SupportTicket.CLOSED})
    ticket_a.refresh_from_db()
    check(ticket_a.status == SupportTicket.OPEN,
          "y mandar status=closed a mano en el POST no lo cierra",
          f"HTTP {r.status_code} / {ticket_a.status}")

    # --- 4. Sí puede ampliar la descripción --------------------------------
    print("\n=== 4. Puede agregar más información a su ticket ===")
    original = ticket_a.description
    ampliada = original + "\n\nAmpliacion: pasa solo con los remitos de la sucursal 2."
    r = guardar(sesion_a, f"{TICKETS}/{ticket_a.pk}/change/", {
        "subject": ticket_a.subject, "description": ampliada})
    ticket_a.refresh_from_db()
    check(r.status_code == 302 and ticket_a.description == ampliada,
          "la ampliación se guarda", f"HTTP {r.status_code}")

    fila = SupportTicket.history.filter(id=ticket_a.pk).first()
    cambios = {c.field: (c.old, c.new) for c in fila.diff_against(fila.prev_record).changes}
    check(fila.history_user_id == admin_a.pk and "description" in cambios,
          "y el historial (8.2) guarda el texto anterior y quién lo amplió",
          str(fila.history_user))
    check(cambios["description"][0] == original,
          "el texto original NO se pierde al editar", cambios["description"][0][:40])

    # --- 5. Aislamiento entre empresas -------------------------------------
    print("\n=== 5. Aislamiento: la empresa A y la empresa B ===")
    r = guardar(sesion_b, f"{TICKETS}/add/", {
        "subject": f"Quiero sumar dos operadores {TAG}",
        "description": "Necesito dar de alta dos operadores nuevos."})
    check(r.status_code == 302, "el admin de la empresa B abre el suyo",
          f"HTTP {r.status_code}")
    ticket_b = SupportTicket.objects.filter(company=empresa_b).first()
    tickets.append(ticket_b)
    check(ticket_b is not None and ticket_b.company_id == empresa_b.pk,
          "y queda en la empresa B", str(ticket_b.company))

    html, _ = pantalla(sesion_a, f"{TICKETS}/")
    check(ticket_a.subject in html, "en su listado, A ve su ticket")
    check(ticket_b.subject not in html and empresa_b.name not in html,
          "CRITERIO: y NO ve el de la empresa B, ni el nombre de la empresa B")
    check("Por Empresa" not in html,
          "el filtro por empresa no se le muestra (no tiene sentido con una sola)")

    r = sesion_a.get(f"{ADMIN}{TICKETS}/{ticket_b.pk}/change/", timeout=30,
                     allow_redirects=False)
    check(r.status_code == 302,
          "CRITERIO: abrir la ficha del ticket de B por URL da el redirect de «no existe»",
          f"HTTP {r.status_code}")

    guardar(sesion_a, f"{TICKETS}/{ticket_b.pk}/change/",
            {"subject": "SECUESTRADO", "description": "x"})
    ticket_b.refresh_from_db()
    check(ticket_b.subject != "SECUESTRADO",
          "y un POST sobre el ticket ajeno no lo modifica", ticket_b.subject)

    r = sesion_a.get(f"{ADMIN}{TICKETS}/{ticket_b.pk}/history/", timeout=30,
                     allow_redirects=False)
    check(r.status_code == 404, "el historial del ticket ajeno tampoco se abre (8.2)",
          f"HTTP {r.status_code}")

    r = sesion_a.get(f"{ADMIN}{TICKETS}/{ticket_a.pk}/delete/", timeout=30,
                     allow_redirects=False)
    check(r.status_code == 403,
          "un ticket no se borra desde la empresa: es el registro de un pedido",
          f"HTTP {r.status_code}")

    # --- 6. Friese los ve todos y los resuelve -----------------------------
    print("\n=== 6. El superadmin los ve todos y mueve el estado ===")
    html, _ = pantalla(sesion_root, f"{TICKETS}/")
    check(ticket_a.subject in html and ticket_b.subject in html,
          "el superadmin ve los tickets de las dos empresas")
    check(empresa_a.name in html and empresa_b.name in html,
          "con su empresa en el listado")
    check("Por Empresa" in html, "y conserva el filtro por empresa")

    _, nombres = pantalla(sesion_root, f"{TICKETS}/{ticket_a.pk}/change/")
    check("status" in nombres, "en la ficha SÍ puede editar el estado")
    r = guardar(sesion_root, f"{TICKETS}/{ticket_a.pk}/change/", {
        "company": empresa_a.pk, "subject": ticket_a.subject,
        "description": ticket_a.description, "status": SupportTicket.IN_PROGRESS})
    ticket_a.refresh_from_db()
    check(r.status_code == 302 and ticket_a.status == SupportTicket.IN_PROGRESS,
          "y al resolverlo el estado avanza", f"HTTP {r.status_code} / {ticket_a.status}")

    fila = SupportTicket.history.filter(id=ticket_a.pk).first()
    check(fila.history_user_id == superadmin.pk and fila.status == SupportTicket.IN_PROGRESS,
          "el historial deja quién movió el estado", str(fila.history_user))

    html, _ = pantalla(sesion_a, f"{TICKETS}/{ticket_a.pk}/change/")
    check("En curso" in html, "y la empresa ve el estado nuevo en su ficha")

    # --- 7. Un usuario del panel sin empresa -------------------------------
    print("\n=== 7. Borde: staff sin empresa ===")
    pass_huerfano = secrets.token_urlsafe(18)
    huerfano = User.objects.create_user(
        username=f"{TAG.lower()}_sin_empresa", password=pass_huerfano,
        is_staff=True, email=f"{TAG.lower()}c@friese.test")
    huerfano.groups.add(grupo)
    usuarios.append(huerfano)
    sesion_h, _ = entrar_al_admin(f"{TAG.lower()}_sin_empresa", pass_huerfano)
    html, _ = pantalla(sesion_h, f"{TICKETS}/")
    check(ticket_a.subject not in html and ticket_b.subject not in html,
          "un staff sin empresa no ve ningún ticket")
    r = sesion_h.get(f"{ADMIN}{TICKETS}/add/", timeout=30, allow_redirects=False)
    check(r.status_code == 403, "y no puede abrir uno (no tendría empresa a la cual ir)",
          f"HTTP {r.status_code}")

    # --- 8. Cómo se ve en el panel -----------------------------------------
    print("\n=== 8. Cómo se ve en el panel ===")
    nav = Browser(mobile=False)
    nav.send("Emulation.setDeviceMetricsOverride", {
        "width": 1440, "height": 900, "deviceScaleFactor": 1, "mobile": False})
    nav.goto(f"{ADMIN}/login/?next=/admin/")
    nav.wait("document.querySelector('#id_username')", label="form de login")
    nav.fill("#id_username", f"{TAG.lower()}_admin_a")
    nav.fill("#id_password", pass_a)
    nav.js("document.querySelector('#login-form').submit()")
    nav.wait("document.querySelector('#user-tools')", label="entrada al panel")

    nav.goto(f"{ADMIN}{TICKETS}/")
    nav.wait("document.querySelector('#content')", label="listado de tickets")
    listado = nav.text("#content")
    check("Ticket de soporte" in listado and ticket_a.subject in listado,
          "el listado de la empresa muestra sus tickets, en castellano")
    nav.shot("s01-tickets-listado")

    nav.goto(f"{ADMIN}{TICKETS}/{ticket_a.pk}/change/")
    nav.wait("document.querySelector('#id_description')", label="ficha del ticket")
    ficha = nav.text("#content")
    check("Asunto" in ficha and "Estado" in ficha and "En curso" in ficha,
          "y la ficha muestra el estado que puso Friese, sin desplegable")
    nav.shot("s02-ticket-ficha")

    nav.goto(f"{ADMIN}{TICKETS}/add/")
    nav.wait("document.querySelector('#id_subject')", label="alta de ticket")
    check("Estado" not in nav.text("#content"),
          "y el alta solo pide asunto y descripción")
    nav.shot("s03-ticket-alta")
finally:
    ids_tickets = [t.pk for t in tickets if t]
    ids_usuarios = [u.pk for u in usuarios if u]
    ids_empresas = [c.pk for c in empresas if c]
    # Los tickets primero: `created_by` es PROTECT, así que los usuarios no se
    # borran mientras exista un ticket suyo.
    SupportTicket.objects.filter(pk__in=ids_tickets).delete()
    User.objects.filter(pk__in=ids_usuarios).delete()
    Company.objects.filter(pk__in=ids_empresas).delete()
    borradas = borrar_historial(empresas=ids_empresas, usuarios=ids_usuarios)
    borradas += SupportTicket.history.filter(id__in=ids_tickets).delete()[0]

    if nav:
        nav.close()
    servidor.terminate()
    try:
        servidor.wait(timeout=10)
    except Exception:
        servidor.kill()

print(f"\n  limpieza: {borradas} filas de historial borradas; quedan "
      f"{SupportTicket.objects.filter(subject__contains=TAG).count()} tickets y "
      f"{SupportTicket.history.filter(subject__contains=TAG).count()} filas con la marca {TAG}")
sys.exit(summary("tickets de soporte (9.1)"))
