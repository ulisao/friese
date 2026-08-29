"""Criterio de aceptación de la 10.2 — resumen del mes en el índice del panel.

Los números que ve el admin de una empresa al entrar a `/admin/` tienen que coincidir
con los datos REALES de su empresa, y un admin de la empresa A no puede ver jamás los
de la empresa B. Se prueba leyendo los números que RENDERIZA el panel por HTTP y
comparándolos contra consultas independientes a la base — no contra el mismo cálculo
que hace la vista.

    python smoke_tests/dashboard_metrics.py

Levanta su propio server local contra la base de siempre, crea sus datos con la marca
SMOKE102 —dos empresas, para probar el aislamiento igual que en la 4.1— y los borra al
final, incluidas las filas de historial que generó (8.2). Los remitos se crean SIN
`receiver_email`, así el signal de despacho no manda ningún email al mundo real.
"""

import os
import re
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

from django.utils import timezone  # noqa: E402
from django.utils.formats import date_format  # noqa: E402

from companies.models import Company, UsageLog  # noqa: E402
from shipments.models import Evidence, Shipment  # noqa: E402
from users.groups import ensure_company_admin_group  # noqa: E402
from users.models import User  # noqa: E402

from browser import Browser  # noqa: E402
from e2e import borrar_historial, check, summary  # noqa: E402

PYTHON = os.path.join(BASE_DIR, "venv", "Scripts", "python.exe")
PUERTO = 8028
LOCAL = f"http://127.0.0.1:{PUERTO}"
ADMIN = f"{LOCAL}/admin"
TAG = "SMOKE102"

# Los mismos límites del mes que usa la vista, calculados acá aparte para no
# depender del código que se está probando.
AHORA = timezone.localtime()
INICIO_MES = AHORA.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
FIN_MES = (INICIO_MES + timedelta(days=32)).replace(day=1)
CLAVE_MES = INICIO_MES.strftime("%Y-%m")
MES_PASADO = INICIO_MES - timedelta(days=1)


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


def indice(sesion, query=""):
    """(HTML del índice, {etiqueta de la tarjeta: número}) tal como los dibuja el panel.

    Se leen los números RENDERIZADOS, no los que devuelve la función de métricas: lo
    que importa es lo que termina viendo el usuario en la pantalla.
    """
    r = sesion.get(f"{ADMIN}/{query}", timeout=30)
    r.raise_for_status()
    tarjetas = {
        etiqueta.strip(): int(numero)
        for numero, etiqueta in re.findall(
            r'friese-kpi-numero">(\d+)</span>\s*'
            r'<span class="friese-kpi-label">([^<]+)</span>',
            r.text,
        )
    }
    return r.text, tarjetas


def esperado(company=None):
    """Los números que TIENEN que salir, contados aparte con consultas propias."""
    remitos = Shipment.objects.filter(
        dispatched_at__gte=INICIO_MES, dispatched_at__lt=FIN_MES
    )
    usos = UsageLog.objects.filter(month=CLAVE_MES)
    if company is not None:
        remitos = remitos.filter(company=company)
        usos = usos.filter(company=company)
    return {
        "Remitos despachados": remitos.count(),
        "Pendientes de respuesta": remitos.filter(status=Shipment.DISPATCHED).count(),
        "Aceptados": remitos.filter(status=Shipment.ACCEPTED).count(),
        "En disputa": remitos.filter(status=Shipment.DISPUTED).count(),
        "Fotos de evidencia": sum(u.photos_uploaded for u in usos),
    }


def crear_remito(company, operador, status, dispatched_at):
    return Shipment.objects.create(
        company=company, operator=operador,
        receiver_name=f"Receptor {TAG}",
        # Sin receiver_email a propósito: el signal de despacho no manda nada.
        status=status, dispatched_at=dispatched_at,
    )


servidor = subprocess.Popen(
    [PYTHON, "manage.py", "runserver", f"127.0.0.1:{PUERTO}", "--noreload"],
    cwd=BASE_DIR, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

nav = None
empresas = []
usuarios = []
remitos = []
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

    # --- Datos de prueba ---------------------------------------------------
    print("=== 0. Datos de prueba ===")
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
    operador_a = User.objects.create_user(
        username=f"{TAG.lower()}_op_a", password=secrets.token_urlsafe(18),
        company=empresa_a, role=User.OPERATOR)
    operador_b = User.objects.create_user(
        username=f"{TAG.lower()}_op_b", password=secrets.token_urlsafe(18),
        company=empresa_b, role=User.OPERATOR)
    usuarios += [admin_a, admin_b, operador_a, operador_b]

    # Empresa A, mes en curso: 3 pendientes, 2 aceptados, 1 en disputa = 6.
    for _ in range(3):
        remitos.append(crear_remito(empresa_a, operador_a, Shipment.DISPATCHED, AHORA))
    for _ in range(2):
        remitos.append(crear_remito(empresa_a, operador_a, Shipment.ACCEPTED, AHORA))
    remitos.append(crear_remito(empresa_a, operador_a, Shipment.DISPUTED, AHORA))
    # Los dos que NO tienen que contar: un borrador (nunca salió del depósito) y
    # un despachado el mes pasado.
    borrador = Shipment.objects.create(
        company=empresa_a, operator=operador_a, receiver_name=f"Borrador {TAG}")
    remitos.append(borrador)
    viejo = crear_remito(empresa_a, operador_a, Shipment.DISPATCHED, MES_PASADO)
    remitos.append(viejo)

    # Empresa B: números distintos a los de A, para que un cruce se note.
    remitos.append(crear_remito(empresa_b, operador_b, Shipment.DISPATCHED, AHORA))
    remitos.append(crear_remito(empresa_b, operador_b, Shipment.ACCEPTED, AHORA))

    # Fotos: 4 en A y 1 en B (el signal de evidencia mueve UsageLog.photos_uploaded).
    for n in range(4):
        Evidence.objects.create(shipment=remitos[0], type=Evidence.DISPATCH,
                                file_url=f"https://r2.test/{TAG}/a{n}.jpg")
    Evidence.objects.create(shipment=remitos[-1], type=Evidence.RECEPTION,
                            file_url=f"https://r2.test/{TAG}/b0.jpg")

    espera_a = esperado(empresa_a)
    espera_b = esperado(empresa_b)
    espera_todas = esperado()
    check(espera_a["Remitos despachados"] == 6 and espera_a["Fotos de evidencia"] >= 4,
          "los datos sembrados en A quedaron como se esperaba", str(espera_a))
    check(espera_b["Remitos despachados"] == 2, "y los de B también", str(espera_b))

    sesion_a, r = entrar_al_admin(f"{TAG.lower()}_admin_a", pass_a)
    check(r.status_code == 302, "el admin de la empresa A entra al panel",
          f"HTTP {r.status_code}")
    sesion_b, _ = entrar_al_admin(f"{TAG.lower()}_admin_b", pass_b)
    sesion_root, r = entrar_al_admin(f"{TAG.lower()}_root", pass_super)
    check(r.status_code == 302, "y el superadmin también", f"HTTP {r.status_code}")

    # --- 1. Los números de la empresa A ------------------------------------
    print("\n=== 1. Los números que ve el admin de la empresa A ===")
    html_a, tarjetas_a = indice(sesion_a)
    check(bool(tarjetas_a), "el índice del panel muestra el resumen del mes",
          str(tarjetas_a))
    for etiqueta, valor in espera_a.items():
        check(tarjetas_a.get(etiqueta) == valor,
              f"CRITERIO — «{etiqueta}» coincide con los datos reales de A",
              f"panel {tarjetas_a.get(etiqueta)} vs base {valor}")
    check(
        tarjetas_a["Pendientes de respuesta"] + tarjetas_a["Aceptados"]
        + tarjetas_a["En disputa"] == tarjetas_a["Remitos despachados"],
        "y los tres estados suman exactamente el total")

    titulo = re.search(r"Resumen de [^<—]+", html_a).group(0).strip()
    mes_en_letras = date_format(INICIO_MES, "F Y")
    check(titulo.lower() == f"resumen de {mes_en_letras}".lower(),
          "el título dice de qué mes son los números", titulo)

    # --- 2. Lo que NO cuenta -----------------------------------------------
    print("\n=== 2. Un borrador y un remito del mes pasado no entran ===")
    total_con_extras = Shipment.objects.filter(company=empresa_a).count()
    check(total_con_extras == tarjetas_a["Remitos despachados"] + 2,
          "la empresa A tiene 2 remitos más que los que cuenta el resumen",
          f"{total_con_extras} en la base vs {tarjetas_a['Remitos despachados']} contados")
    check(borrador.status == Shipment.DRAFT and borrador.dispatched_at is None,
          "uno es el borrador sin despachar")
    check(viejo.dispatched_at < INICIO_MES,
          "y el otro se despachó el mes pasado", str(viejo.dispatched_at.date()))

    # --- 3. Aislamiento multi-tenant (CRITERIO) ----------------------------
    print("\n=== 3. Aislamiento: A no ve nada de B ===")
    _, tarjetas_b = indice(sesion_b)
    check(tarjetas_b == espera_b, "el admin de B ve los números de B", str(tarjetas_b))
    check(tarjetas_a["Remitos despachados"] != tarjetas_b["Remitos despachados"],
          "y los dos resúmenes son distintos, así que un cruce se notaría")
    check(empresa_b.name not in html_a and f"{TAG} B" not in html_a,
          "el índice de A no menciona a la empresa B")
    check('name="empresa"' not in html_a,
          "y el admin de empresa no tiene desplegable de empresas: no hay qué elegir")

    _, tarjetas_forzadas = indice(sesion_a, f"?empresa={empresa_b.pk}")
    check(tarjetas_forzadas == espera_a,
          "CRITERIO — A pidiendo ?empresa=B por URL sigue viendo SUS números",
          str(tarjetas_forzadas))
    _, tarjetas_basura = indice(sesion_a, "?empresa=no-soy-un-id")
    check(tarjetas_basura == espera_a, "y un valor inventado tampoco lo mueve")

    # --- 4. El superadmin de Friese ----------------------------------------
    print("\n=== 4. El superadmin ve todas y puede filtrar ===")
    html_root, tarjetas_root = indice(sesion_root)
    check(tarjetas_root == espera_todas,
          "sin filtro ve el consolidado de todas las empresas", str(tarjetas_root))
    check(tarjetas_root["Remitos despachados"]
          >= espera_a["Remitos despachados"] + espera_b["Remitos despachados"],
          "que incluye los remitos de A y los de B")
    check('name="empresa"' in html_root and empresa_a.name in html_root
          and empresa_b.name in html_root,
          "y tiene el desplegable con las empresas")

    _, tarjetas_root_a = indice(sesion_root, f"?empresa={empresa_a.pk}")
    check(tarjetas_root_a == espera_a,
          "filtrando por la empresa A ve exactamente los números de A",
          str(tarjetas_root_a))
    html_root_b, tarjetas_root_b = indice(sesion_root, f"?empresa={empresa_b.pk}")
    check(tarjetas_root_b == espera_b, "y por la B, los de B", str(tarjetas_root_b))
    check(empresa_b.name in re.search(r"Resumen de [^<]*", html_root_b).group(0),
          "con el nombre de la empresa filtrada en el título")
    _, tarjetas_root_fantasma = indice(sesion_root, "?empresa=999999999")
    check(tarjetas_root_fantasma == espera_todas,
          "una empresa que no existe vuelve al consolidado, sin romper la pantalla")

    # --- 5. Fotos de evidencia (UsageLog) ----------------------------------
    print("\n=== 5. Las fotos salen del UsageLog que ya existe ===")
    uso_a = UsageLog.objects.get(company=empresa_a, month=CLAVE_MES)
    check(tarjetas_a["Fotos de evidencia"] == uso_a.photos_uploaded,
          "el número de fotos de A es su UsageLog del mes",
          f"panel {tarjetas_a['Fotos de evidencia']} vs UsageLog {uso_a.photos_uploaded}")
    antes = uso_a.photos_uploaded
    foto = Evidence.objects.create(shipment=remitos[0], type=Evidence.DISPATCH,
                                   file_url=f"https://r2.test/{TAG}/a-extra.jpg")
    uso_a.refresh_from_db()
    _, tarjetas_despues = indice(sesion_a)
    check(uso_a.photos_uploaded == antes + 1
          and tarjetas_despues["Fotos de evidencia"] == antes + 1,
          "una foto nueva sube el contador del panel en 1, sin contadores propios",
          f"{antes} a {tarjetas_despues['Fotos de evidencia']}")
    foto.delete()

    # --- 6. Borde: staff sin empresa ---------------------------------------
    print("\n=== 6. Borde: staff sin empresa ===")
    pass_huerfano = secrets.token_urlsafe(18)
    huerfano = User.objects.create_user(
        username=f"{TAG.lower()}_sin_empresa", password=pass_huerfano,
        is_staff=True, email=f"{TAG.lower()}c@friese.test")
    huerfano.groups.add(grupo)
    usuarios.append(huerfano)
    sesion_h, _ = entrar_al_admin(f"{TAG.lower()}_sin_empresa", pass_huerfano)
    html_h, tarjetas_h = indice(sesion_h)
    check(not tarjetas_h and "friese-dash" not in html_h,
          "un staff sin empresa no ve ningún número (no pertenece a ningún tenant)")
    check("<h1" in html_h or "id=\"content\"" in html_h,
          "pero el índice sigue abriendo normalmente", f"HTTP OK, {len(html_h)} bytes")

    # --- 7. Cómo se ve en el panel -----------------------------------------
    print("\n=== 7. Cómo se ve en el panel ===")
    nav = Browser(mobile=False)
    nav.send("Emulation.setDeviceMetricsOverride", {
        "width": 1440, "height": 900, "deviceScaleFactor": 1, "mobile": False})
    nav.goto(f"{ADMIN}/login/?next=/admin/")
    nav.wait("document.querySelector('#id_username')", label="form de login")
    nav.fill("#id_username", f"{TAG.lower()}_admin_a")
    nav.fill("#id_password", pass_a)
    nav.js("document.querySelector('#login-form').submit()")
    nav.wait("document.querySelector('#user-tools')", label="entrada al panel")

    nav.goto(f"{ADMIN}/")
    nav.wait("document.querySelector('.friese-dash')", label="resumen del mes")
    resumen = nav.text(".friese-dash")
    check("Remitos despachados" in resumen and "Pendientes de respuesta" in resumen
          and "Fotos de evidencia" in resumen,
          "el resumen se ve arriba del índice, en castellano", resumen.split("\n")[0][:80])
    check(nav.js("document.querySelectorAll('.friese-kpi').length") == 5,
          "con una tarjeta por número: total, los tres estados y las fotos")
    check(nav.js(
        "getComputedStyle(document.querySelector('.friese-kpi-numero')).fontWeight"
    ) in ("700", "bold"),
        "y el tema de la 7.3 aplicado (el número se dibuja destacado)")
    nav.shot("d01-dashboard-empresa")

    # Cambio de usuario: se limpia la sesión por CDP (el logout del admin de
    # Django 5.1 solo acepta POST).
    nav.send("Network.clearBrowserCookies")
    nav.goto(f"{ADMIN}/login/?next=/admin/")
    nav.wait("document.querySelector('#id_username')", label="form de login")
    nav.fill("#id_username", f"{TAG.lower()}_root")
    nav.fill("#id_password", pass_super)
    nav.js("document.querySelector('#login-form').submit()")
    nav.wait("document.querySelector('#user-tools')", label="entrada del superadmin")
    nav.goto(f"{ADMIN}/?empresa={empresa_a.pk}")
    nav.wait("document.querySelector('#friese-empresa')", label="desplegable de empresas")
    check(empresa_a.name in nav.text(".friese-dash"),
          "el superadmin ve el filtro por empresa con la empresa elegida")
    nav.shot("d02-dashboard-superadmin")
finally:
    ids_remitos = [s.pk for s in remitos if s]
    ids_usuarios = [u.pk for u in usuarios if u]
    ids_empresas = [c.pk for c in empresas if c]
    # Los remitos primero: `operator` es PROTECT, así que el usuario no se borra
    # mientras exista un remito suyo. La evidencia se va por CASCADE.
    Shipment.objects.filter(pk__in=ids_remitos).delete()
    UsageLog.objects.filter(company_id__in=ids_empresas).delete()
    User.objects.filter(pk__in=ids_usuarios).delete()
    Company.objects.filter(pk__in=ids_empresas).delete()
    borradas = borrar_historial(empresas=ids_empresas, usuarios=ids_usuarios,
                               remitos=ids_remitos)

    if nav:
        nav.close()
    servidor.terminate()
    try:
        servidor.wait(timeout=10)
    except Exception:
        servidor.kill()

print(f"\n  limpieza: {borradas} filas de historial borradas; quedan "
      f"{Shipment.objects.filter(receiver_name__contains=TAG).count()} remitos y "
      f"{Company.objects.filter(name__contains=TAG).count()} empresas con la marca {TAG}")
sys.exit(summary("resumen del mes en el panel (10.2)"))
