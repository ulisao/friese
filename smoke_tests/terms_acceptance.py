"""Criterio de aceptación de la 8.3 — registro del momento de aceptación del contrato.

Los dos campos nuevos de `Company` (`terms_accepted_at` y `terms_accepted_version`)
existen, se ven y se editan DESDE EL DJANGO ADMIN, tanto al dar de alta una empresa
como al editarla después. Se prueba contra los formularios reales por HTTP, que es el
único camino por el que se van a cargar: la aceptación pasa fuera del sistema y estos
campos los completa a mano el superadmin de Friese al cerrar cada cliente.

    python smoke_tests/terms_acceptance.py

Levanta su propio server local contra la base de siempre, crea sus datos con la marca
SMOKE83 y los borra al final, incluidas las filas de historial que generó (8.2).
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

from django.utils import timezone  # noqa: E402
from django.utils.formats import localize  # noqa: E402
from django.utils.html import escape  # noqa: E402

from companies.models import Company  # noqa: E402
from users.groups import ensure_company_admin_group  # noqa: E402
from users.models import User  # noqa: E402

from browser import Browser  # noqa: E402
from e2e import borrar_historial, check, summary  # noqa: E402

PYTHON = os.path.join(BASE_DIR, "venv", "Scripts", "python.exe")
PUERTO = 8025
LOCAL = f"http://127.0.0.1:{PUERTO}"
ADMIN = f"{LOCAL}/admin"
TAG = "SMOKE83"

# El admin parte el DateTimeField en dos inputs (fecha y hora) y con LANGUAGE_CODE
# 'es-ar' la fecha se escribe DD/MM/AAAA. Se manda tal cual la tipearía una persona.
FECHA = "05/03/2026"
HORA = "16:45:00"
CAMPOS_TERMS = {"terms_accepted_at_0", "terms_accepted_at_1", "terms_accepted_version"}


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
    """Devuelve el HTML de una pantalla del admin y los names de sus inputs.

    Los names sirven para distinguir un campo EDITABLE (tiene input) de uno que
    el admin dibuja de solo lectura (aparece el valor, no el input).
    """
    r = sesion.get(f"{ADMIN}{path}", timeout=30)
    r.raise_for_status()
    nombres = set(re.findall(r'<(?:input|select|textarea)[^>]*\bname="([^"]+)"', r.text))
    return r.text, nombres


def guardar(sesion, path, datos):
    """Envía el formulario del admin con `datos`. Devuelve la respuesta.

    El form de Company no tiene inlines, así que los campos se mandan explícitos
    en vez de releer la pantalla: es todo lo que un navegador enviaría.
    """
    url = f"{ADMIN}{path}"
    sesion.get(url, timeout=30).raise_for_status()
    datos = dict(datos)
    datos["csrfmiddlewaretoken"] = sesion.cookies["csrftoken"]
    datos["_save"] = "Grabar"
    r = sesion.post(url, data=datos, headers={"Referer": url},
                    allow_redirects=False, timeout=60)
    if r.status_code == 200:
        # El admin re-renderiza el form con los errores en vez de redirigir.
        errores = re.findall(r'<ul class="errorlist[^"]*"[^>]*>(.*?)</ul>', r.text, re.S)
        if errores:
            print("    errores del formulario:", " | ".join(
                re.sub(r"<[^>]+>", " ", e).strip() for e in errores)[:400])
    return r


def form_empresa(**cambios):
    """Los campos del form de Company, con los valores de base ya puestos."""
    datos = {"name": "", "email": "", "phone": "", "plan": "",
             "is_active": "on", "trial_shipments_remaining": "10",
             "terms_accepted_at_0": "", "terms_accepted_at_1": "",
             "terms_accepted_version": ""}
    datos.update(cambios)
    return datos


servidor = subprocess.Popen(
    [PYTHON, "manage.py", "runserver", f"127.0.0.1:{PUERTO}", "--noreload"],
    cwd=BASE_DIR, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

nav = None
empresas = []
usuarios = []
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

    pass_super = secrets.token_urlsafe(18)
    superadmin = User.objects.create_superuser(
        username=f"{TAG.lower()}_root", password=pass_super,
        email=f"{TAG.lower()}root@friese.test")
    usuarios.append(superadmin)

    sesion, r = entrar_al_admin(f"{TAG.lower()}_root", pass_super)
    check(r.status_code == 302, "el superadmin entra al panel", f"HTTP {r.status_code}")

    # --- 1. Los campos existen y son opcionales ---------------------------
    print("\n=== 1. Los dos campos existen y pueden quedar vacíos ===")
    f_at = Company._meta.get_field("terms_accepted_at")
    f_ver = Company._meta.get_field("terms_accepted_version")
    check(f_at.get_internal_type() == "DateTimeField" and f_at.null and f_at.blank,
          "terms_accepted_at es fecha/hora y admite quedar vacío",
          f"{f_at.get_internal_type()} null={f_at.null} blank={f_at.blank}")
    check(f_ver.get_internal_type() == "CharField" and f_ver.blank and f_ver.max_length <= 50,
          "terms_accepted_version es un string corto y admite quedar vacío",
          f"max_length={f_ver.max_length} blank={f_ver.blank}")

    # --- 2. Alta de una empresa con el contrato ya aceptado ---------------
    print("\n=== 2. Al DAR DE ALTA una empresa desde el admin ===")
    html, nombres = pantalla(sesion, "/companies/company/add/")
    check(CAMPOS_TERMS <= nombres, "el formulario de alta muestra los dos campos",
          sorted(CAMPOS_TERMS & nombres))
    check("Contrato" in html and "Términos de Servicio" in html,
          "bajo una sección que explica para qué son")

    pass_admin = secrets.token_urlsafe(18)
    r = guardar(sesion, "/companies/company/add/", form_empresa(
        name=f"Fletes {TAG} SA",
        email=f"{TAG.lower()}@friese.test",
        terms_accepted_at_0=FECHA,
        terms_accepted_at_1=HORA,
        terms_accepted_version="v1",
        admin_username=f"{TAG.lower()}_admin",
        admin_email=f"{TAG.lower()}a@friese.test",
        admin_password=pass_admin,
        admin_password_confirm=pass_admin,
    ))
    check(r.status_code == 302, "el alta guarda", f"HTTP {r.status_code}")

    empresa = Company.objects.filter(name=f"Fletes {TAG} SA").first()
    check(empresa is not None, "la empresa quedó creada")
    empresas.append(empresa)
    admin_empresa = User.objects.filter(username=f"{TAG.lower()}_admin").first()
    usuarios.append(admin_empresa)
    admin_empresa.groups.add(ensure_company_admin_group())

    local = timezone.localtime(empresa.terms_accepted_at)
    check(local.strftime("%d/%m/%Y") == FECHA and local.strftime("%H:%M:%S") == HORA,
          "se guardó la fecha y hora que se tipeó, en la zona horaria del panel",
          str(local))
    check(empresa.terms_accepted_version == "v1", "y la versión del texto aceptado",
          empresa.terms_accepted_version)

    # --- 3. Editar una empresa ya existente -------------------------------
    print("\n=== 3. Al EDITAR una empresa existente ===")
    vieja = Company.objects.create(name=f"Vieja {TAG} SRL",
                                   email=f"{TAG.lower()}b@friese.test")
    empresas.append(vieja)
    check(vieja.terms_accepted_at is None and vieja.terms_accepted_version == "",
          "una empresa arranca sin aceptación registrada",
          f"{vieja.terms_accepted_at!r} / {vieja.terms_accepted_version!r}")

    html, nombres = pantalla(sesion, f"/companies/company/{vieja.pk}/change/")
    check(CAMPOS_TERMS <= nombres, "el formulario de edición también los muestra",
          sorted(CAMPOS_TERMS & nombres))

    r = guardar(sesion, f"/companies/company/{vieja.pk}/change/", form_empresa(
        name=vieja.name, email=vieja.email,
        terms_accepted_at_0=FECHA, terms_accepted_at_1=HORA,
        terms_accepted_version="v2"))
    check(r.status_code == 302, "la edición guarda", f"HTTP {r.status_code}")
    vieja.refresh_from_db()
    local = timezone.localtime(vieja.terms_accepted_at)
    check(local.strftime("%d/%m/%Y %H:%M:%S") == f"{FECHA} {HORA}"
          and vieja.terms_accepted_version == "v2",
          "el momento de aceptación queda registrado en una empresa ya dada de alta",
          f"{local} / {vieja.terms_accepted_version}")

    r = guardar(sesion, f"/companies/company/{vieja.pk}/change/",
                form_empresa(name=vieja.name, email=vieja.email))
    vieja.refresh_from_db()
    check(r.status_code == 302 and vieja.terms_accepted_at is None
          and vieja.terms_accepted_version == "",
          "y se puede volver a dejar en blanco si se cargó por error",
          f"HTTP {r.status_code} / {vieja.terms_accepted_at!r}")

    # --- 4. El cambio queda auditado (8.2) --------------------------------
    print("\n=== 4. Queda auditado quién lo cargó (8.2) ===")
    fila = Company.history.filter(id=vieja.pk).first()
    cambiados = {c.field: (c.old, c.new)
                 for c in fila.diff_against(fila.prev_record).changes}
    check(fila.history_user_id == superadmin.pk,
          "el historial de la empresa registra quién tocó la aceptación",
          str(fila.history_user))
    check(set(cambiados) == {"terms_accepted_at", "terms_accepted_version"},
          "y qué campos cambió, con su valor anterior", cambiados)

    # --- 5. Es un registro de Friese, no del cliente ----------------------
    print("\n=== 5. El admin de la empresa lo ve pero no lo edita ===")
    sesion_cliente, r = entrar_al_admin(f"{TAG.lower()}_admin", pass_admin)
    check(r.status_code == 302, "el admin de la empresa entra al panel",
          f"HTTP {r.status_code}")

    visible = escape(localize(timezone.localtime(empresa.terms_accepted_at)))
    html, nombres = pantalla(sesion_cliente, f"/companies/company/{empresa.pk}/change/")
    check("Aceptación de los Términos" in html and visible in html,
          "ve en su ficha cuándo aceptó los Términos", visible)
    check(not (CAMPOS_TERMS & nombres),
          "pero le llegan de solo lectura, sin input para editarlos",
          sorted(CAMPOS_TERMS & nombres))

    r = guardar(sesion_cliente, f"/companies/company/{empresa.pk}/change/", form_empresa(
        name=empresa.name, email=empresa.email,
        terms_accepted_at_0="01/01/2020", terms_accepted_at_1="00:00:00",
        terms_accepted_version="INVENTADA"))
    empresa.refresh_from_db()
    check(empresa.terms_accepted_version == "v1"
          and timezone.localtime(empresa.terms_accepted_at).strftime("%d/%m/%Y") == FECHA,
          "y mandarlos a mano en el POST tampoco los cambia",
          f"HTTP {r.status_code} / {empresa.terms_accepted_version}")

    # --- 6. Se ve en el listado de empresas -------------------------------
    print("\n=== 6. Visible en el listado ===")
    html, _ = pantalla(sesion, f"/companies/company/?q={TAG}")
    check("Aceptación de los Términos" in html,
          "el listado del superadmin tiene la columna de aceptación")
    check(visible in html, "con la fecha de la empresa que ya aceptó", visible)
    check(f"Vieja {TAG} SRL" in html, "y la que no aceptó aparece igual, con la celda vacía")

    # --- 7. Cómo se ve en el panel ----------------------------------------
    print("\n=== 7. Cómo se ve en el panel ===")
    nav = Browser(mobile=False)
    nav.send("Emulation.setDeviceMetricsOverride", {
        "width": 1440, "height": 900, "deviceScaleFactor": 1, "mobile": False})
    nav.goto(f"{ADMIN}/login/?next=/admin/")
    nav.wait("document.querySelector('#id_username')", label="form de login")
    nav.fill("#id_username", f"{TAG.lower()}_root")
    nav.fill("#id_password", pass_super)
    nav.js("document.querySelector('#login-form').submit()")
    nav.wait("document.querySelector('#user-tools')", label="entrada al panel")

    nav.goto(f"{ADMIN}/companies/company/{empresa.pk}/change/")
    nav.wait("document.querySelector('#id_terms_accepted_version')",
             label="campo de versión en la ficha")
    ficha = nav.text("#content")
    check("Aceptación de los Términos" in ficha and "Versión aceptada" in ficha,
          "la ficha de la empresa muestra los dos campos en castellano")
    check(bool(nav.js("document.querySelector('#id_terms_accepted_version').value === 'v1'")),
          "con la versión que se había cargado")
    nav.shot("t01-empresa-terminos")

    nav.goto(f"{ADMIN}/companies/company/add/")
    nav.wait("document.querySelector('#id_terms_accepted_version')", label="alta de empresa")
    check("Contrato" in nav.text("#content"),
          "y el alta los agrupa bajo la sección Contrato")
    nav.shot("t02-alta-contrato")
finally:
    # --- Limpieza: objetos Y su historial ---------------------------------
    ids_usuarios = [u.pk for u in usuarios if u]
    ids_empresas = [c.pk for c in empresas if c]
    User.objects.filter(pk__in=ids_usuarios).delete()
    Company.objects.filter(pk__in=ids_empresas).delete()
    # El historial sobrevive al borrado de su objeto (8.2): las filas de esta
    # corrida se limpian aparte, o la auditoría queda llena de empresas que
    # nunca existieron.
    borradas = borrar_historial(empresas=ids_empresas, usuarios=ids_usuarios)

    if nav:
        nav.close()
    servidor.terminate()
    try:
        servidor.wait(timeout=10)
    except Exception:
        servidor.kill()

print(f"\n  limpieza: {borradas} filas de historial borradas; quedan "
      f"{Company.objects.filter(name__contains=TAG).count()} empresas y "
      f"{Company.history.filter(name__contains=TAG).count()} filas con la marca {TAG}")
sys.exit(summary("aceptación de los Términos (8.3)"))
