"""Tarea 7.3 — verificación del reskin del panel de administración.

Levanta el backend REAL (Django en :8000, contra Supabase) y recorre el panel con
Chrome headless a 1440x900 —el panel es de escritorio, no mobile— como los dos
perfiles que lo usan: el admin de una empresa cliente y el superadmin de Friese.

Se mide sobre los estilos COMPUTADOS del navegador, no sobre el CSS escrito: que
el archivo exista no prueba que se haya aplicado. De paso se audita el contraste
real de cada par texto/fondo contra el mínimo de WCAG AA.

Los dos usuarios de prueba se crean al principio y se borran al final; los datos
de la empresa demo no se tocan.
"""

import os
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
from shipments.models import Shipment  # noqa: E402
from users.groups import ensure_company_admin_group  # noqa: E402
from users.models import User  # noqa: E402

from browser import Browser  # noqa: E402
from e2e import check, summary  # noqa: E402

PYTHON = os.path.join(BASE_DIR, "venv", "Scripts", "python.exe")
ADMIN = "http://127.0.0.1:8000/admin"
TAG = "smoke73"

# Paleta de docs/diseno.md, tal como la devuelve getComputedStyle.
BG = "rgb(26, 26, 34)"        # #1A1A22 fondo base
SURFACE = "rgb(36, 36, 46)"   # #24242E superficies elevadas
INDIGO = "rgb(79, 70, 229)"   # #4F46E5 indigo funcional
GOLD = "rgb(214, 172, 49)"    # #D6AC31 dorado de marca


def contraste(fg, bg):
    """Ratio de contraste WCAG entre dos colores 'rgb(r, g, b)'."""
    def luminancia(color):
        nums = [int(n) for n in color.replace("rgba", "rgb").split("(")[1].split(")")[0].split(",")[:3]]
        canales = []
        for n in nums:
            c = n / 255
            canales.append(c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4)
        return 0.2126 * canales[0] + 0.7152 * canales[1] + 0.0722 * canales[2]

    a, b = luminancia(fg), luminancia(bg)
    return (max(a, b) + 0.05) / (min(a, b) + 0.05)


def estilo(nav, selector, prop):
    return nav.js(
        f"getComputedStyle(document.querySelector({selector!r})).getPropertyValue({prop!r})"
    )


def login(nav, usuario, password):
    # Con sesión abierta, /admin/login/ redirige al índice y no hay form que
    # completar: se cierra la sesión borrando la cookie antes de entrar.
    nav.send("Network.clearBrowserCookies")
    nav.goto(f"{ADMIN}/login/?next=/admin/")
    nav.wait("document.querySelector('#id_username')", label="form de login")
    nav.fill("#id_username", usuario)
    nav.fill("#id_password", password)
    nav.js("document.querySelector('#login-form').submit()")
    # #content-main también existe en el login: la marca de que entró es la barra
    # de usuario, que solo se dibuja con sesión abierta.
    nav.wait("document.querySelector('#user-tools')", label="entrada al panel")
    nav.wait("document.readyState === 'complete' && document.body.clientWidth > 0",
             label="render terminado")


servidor = subprocess.Popen(
    [PYTHON, "manage.py", "runserver", "127.0.0.1:8000", "--noreload"],
    cwd=BASE_DIR, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
)

nav = None
creados = []
try:
    limite = time.time() + 90
    while time.time() < limite:
        try:
            requests.get(f"{ADMIN}/login/", timeout=5)
            break
        except Exception:
            time.sleep(0.5)
    else:
        raise RuntimeError("no levantó el backend")

    # --- Usuarios de prueba ----------------------------------------------
    empresa = Company.objects.order_by("id").first()
    if empresa is None:
        raise RuntimeError("no hay ninguna empresa en la base para probar el panel")

    pass_admin = secrets.token_urlsafe(18)
    admin_empresa = User.objects.create_user(
        username=f"{TAG}_admin", password=pass_admin, company=empresa,
        role=User.ADMIN, is_staff=True, email=f"{TAG}@friese.test",
    )
    admin_empresa.groups.add(ensure_company_admin_group())
    creados.append(admin_empresa)

    pass_super = secrets.token_urlsafe(18)
    superadmin = User.objects.create_superuser(
        username=f"{TAG}_super", password=pass_super, email=f"{TAG}s@friese.test",
    )
    creados.append(superadmin)

    remito = Shipment.objects.filter(company=empresa).order_by("-id").first()

    nav = Browser(mobile=False)
    # El panel es de escritorio: 1440x900 es la resolución en la que lo va a ver
    # el admin de la empresa.
    nav.send("Emulation.setDeviceMetricsOverride", {
        "width": 1440, "height": 900, "deviceScaleFactor": 1, "mobile": False,
    })

    # --- 1. Login: la marca antes de entrar -------------------------------
    nav.goto(f"{ADMIN}/login/")
    nav.wait("document.querySelector('#login-form')", label="pantalla de login")
    nav.shot("a01-login")

    check(
        nav.js("[...document.styleSheets].some(s => (s.href || '').includes('friese.css'))"),
        "la hoja de estilos de Friese carga en el login",
    )
    check(estilo(nav, "body", "background-color") == BG,
          "el login usa el fondo base #1A1A22", estilo(nav, "body", "background-color"))
    check(estilo(nav, ".login #container", "background-color") == SURFACE,
          "la card del login usa la superficie elevada #24242E")
    check(nav.js("!!document.querySelector('.friese-brand img')"),
          "el logo de Friese está en el login")
    check(nav.js("""(() => {
              const img = document.querySelector('.friese-brand img');
              return img && img.complete && img.naturalWidth > 0;
          })()"""),
          "el archivo del logo se sirve de verdad (no es un 404)")
    check("Panel Friese" in nav.js("document.title"),
          "la pestaña dice «Panel Friese», no «Django site admin»", nav.js("document.title"))
    check(estilo(nav, ".submit-row input[type=submit]", "background-color") == INDIGO,
          "el botón de entrar usa el indigo funcional #4F46E5")
    check(nav.js("""(() => {
              const t = document.querySelector('.theme-toggle');
              return !t || getComputedStyle(t).display === 'none';
          })()"""),
          "el selector de tema claro/oscuro queda oculto (el panel es siempre oscuro)")

    # --- 2. Índice del panel como admin de la empresa ---------------------
    login(nav, admin_empresa.username, pass_admin)
    nav.shot("a02-indice-empresa")

    check(estilo(nav, "#header", "background-color") == SURFACE,
          "el header usa la superficie elevada, no el azul del admin nativo",
          estilo(nav, "#header", "background-color"))
    check(estilo(nav, "#site-name a", "color") == GOLD,
          "el nombre del panel va en el dorado de marca #D6AC31",
          estilo(nav, "#site-name a", "color"))
    check("Panel Friese" in nav.text("#site-name"),
          "el header dice «Panel Friese»", nav.text("#site-name"))
    check(nav.js("!!document.querySelector('#site-name img')"),
          "el logo acompaña al título en el header del panel")
    check(estilo(nav, "body", "background-color") == BG,
          "el cuerpo del panel usa el fondo base #1A1A22")

    secciones = nav.text("#content-main")
    for esperado in ("Remitos", "Empresas", "Catálogo", "Usuarios y accesos",
                     "Sesiones de operadores", "Sesiones abiertas"):
        check(esperado in secciones, f"la sección «{esperado}» aparece en español")
    for ingles in ("Token Blacklist", "Outstanding", "Blacklisted"):
        check(ingles not in secciones,
              f"«{ingles}» ya no aparece en inglés en el índice del panel")
    check("Django" not in nav.text("#header"),
          "no queda ningún «Django» a la vista en el header")

    # Contraste real de los pares que dominan la pantalla.
    pares = [
        ("texto principal sobre el fondo", estilo(nav, "body", "color"),
         estilo(nav, "body", "background-color")),
        ("nombre del panel sobre el header", estilo(nav, "#site-name a", "color"),
         estilo(nav, "#header", "background-color")),
        ("barra de usuario sobre el header", estilo(nav, "#user-tools", "color"),
         estilo(nav, "#header", "background-color")),
        ("links de las secciones sobre la card", estilo(nav, "#content-main a", "color"),
         estilo(nav, ".module", "background-color")),
    ]
    for etiqueta, fg, bg in pares:
        ratio = contraste(fg, bg)
        check(ratio >= 4.5, f"contraste AA — {etiqueta}", f"{ratio:.2f}:1")

    # --- 3. Listado de remitos -------------------------------------------
    nav.goto(f"{ADMIN}/shipments/shipment/")
    nav.wait("document.querySelector('#changelist')", label="listado de remitos")
    nav.shot("a03-remitos-listado")

    # El admin dibuja los encabezados en mayúsculas por CSS, y innerText devuelve
    # el texto ya transformado: se compara sin distinguir caso.
    encabezados = nav.text("#result_list thead").upper()
    for esperado in ("Estado", "Receptor", "Operador", "Empresa"):
        check(esperado.upper() in encabezados,
              f"la columna «{esperado}» está en español", encabezados[:60])
    check("DRAFT" not in encabezados and "DISPATCHED" not in nav.text("#result_list").upper(),
          "ningún estado del remito quedó en inglés en el listado")
    check("Despachado" in nav.text("#changelist-filter"),
          "los filtros de estado también están en español")
    check(estilo(nav, "#changelist-filter", "background-color") == SURFACE,
          "el panel de filtros usa la superficie elevada")
    ratio = contraste(estilo(nav, "div.breadcrumbs", "color"),
                      estilo(nav, "div.breadcrumbs", "background-color"))
    check(ratio >= 4.5, "contraste AA — breadcrumbs", f"{ratio:.2f}:1")
    check(estilo(nav, ".object-tools a", "border-radius") == "6px"
          if nav.js("!!document.querySelector('.object-tools a')") else True,
          "los botones usan el radio del sistema (rounded-md)")

    # --- 4. Ficha de un remito, con la evidencia embebida -----------------
    if remito is not None:
        nav.goto(f"{ADMIN}/shipments/shipment/{remito.pk}/change/")
        nav.wait("document.querySelector('#content-main form')", label="ficha del remito")
        nav.shot("a04-remito-ficha")

        etiquetas = nav.text("#content-main")
        for esperado in ("Receptor", "Estado", "Operador", "Empresa"):
            check(esperado in etiquetas, f"la etiqueta «{esperado}» está en español")
        check(nav.js("!!document.querySelector('.inline-group img')"),
              "la foto de evidencia se sigue viendo embebida en la ficha (tarea 4.2)")

    # --- 4b. Un formulario editable: alta de producto ---------------------
    # El admin de empresa tiene los remitos en SOLO LECTURA (users/groups.py), así
    # que los controles de escritura se miran donde sí puede escribir.
    nav.goto(f"{ADMIN}/catalog/product/add/")
    nav.wait("document.querySelector('.submit-row input[name=_save]')",
             label="alta de producto")
    nav.shot("a05-alta-producto")

    check(estilo(nav, ".submit-row input[name=_save]", "background-color") == INDIGO,
          "el botón de guardar usa el indigo funcional #4F46E5",
          estilo(nav, ".submit-row input[name=_save]", "background-color"))
    check(estilo(nav, ".submit-row input[name=_save]", "border-radius") == "6px",
          "los botones usan el radio del sistema (rounded-md)")
    check(estilo(nav, ".submit-row input[name=_save]", "text-transform") == "none",
          "el botón principal no queda en MAYÚSCULAS junto a los secundarios")
    check(estilo(nav, "#id_name", "background-color") == BG,
          "los campos de texto son oscuros, no blancos",
          estilo(nav, "#id_name", "background-color"))
    ratio = contraste(estilo(nav, "#id_name", "border-top-color"),
                      estilo(nav, "#id_name", "background-color"))
    check(ratio >= 3, "el borde del input se distingue del fondo (WCAG 1.4.11)",
          f"{ratio:.2f}:1")
    for esperado in ("Nombre", "Descripción", "Código de barras", "Unidad"):
        check(esperado in nav.text("#content-main"),
              f"la etiqueta «{esperado}» del producto está en español")

    # --- 5. Alta de empresa como superadmin de Friese ---------------------
    login(nav, superadmin.username, pass_super)
    nav.goto(f"{ADMIN}/companies/company/add/")
    nav.wait("document.querySelector('#content-main form')", label="alta de empresa")
    nav.shot("a06-alta-empresa-superadmin")
    check(estilo(nav, ".module", "background-color") == SURFACE,
          "los fieldsets del alta usan la superficie elevada")
    check("Primer admin de la empresa" in nav.text("#content-main"),
          "el alta de empresa + primer admin sigue funcionando con el tema puesto")

    # --- 6. El panel en un celular ----------------------------------------
    nav.send("Emulation.setDeviceMetricsOverride", {
        "width": 390, "height": 844, "deviceScaleFactor": 2, "mobile": True,
    })
    nav.goto(f"{ADMIN}/shipments/shipment/")
    nav.wait("document.querySelector('#changelist')", label="listado en mobile")
    nav.shot("a07-remitos-mobile")
    check(estilo(nav, "body", "background-color") == BG,
          "el tema se sostiene en el layout responsive del admin")

    nav.send("Network.clearBrowserCookies")
    nav.goto(f"{ADMIN}/login/")
    nav.wait("document.querySelector('#login-form')", label="login en mobile")
    nav.shot("a08-login-mobile")
    check(estilo(nav, ".login #container", "background-color") == SURFACE,
          "la card del login se sostiene en mobile")
    check(estilo(nav, ".login .submit-row input[type=submit]", "text-transform") == "none",
          "el botón de entrar tampoco queda en MAYÚSCULAS en mobile")

    # --- 7. Nada roto en la consola ---------------------------------------
    errores = [e for e in nav.errores_de_consola() if "favicon" not in e.lower()]
    check(not errores, "ninguna carga fallida ni error de consola en todo el recorrido",
          " | ".join(errores)[:200])

finally:
    for usuario in creados:
        usuario.delete()
    if nav is not None:
        nav.close()
    servidor.terminate()
    try:
        servidor.wait(timeout=10)
    except Exception:
        servidor.kill()

sys.exit(summary("reskin del panel de administración"))
