"""Criterio de aceptación de la 10.3 — estados vacíos en todas las pantallas.

Con una empresa RECIÉN CREADA (sin remitos y sin productos) se recorren todas las
rutas de la app y se confirma que ninguna queda en blanco: cada una explica qué pasa
y, donde hay algo que hacer, ofrece el botón que lleva al paso siguiente.

    python smoke_tests/empty_states.py

Corre contra un backend y un frontend LOCALES (Django en :8000 + Vite en :5173, que
proxea /api), como `ui_features.py`. Crea sus datos con la marca SMOKE103 y los borra
al final, historial incluido (8.2).
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

from django.utils import timezone  # noqa: E402

from catalog.models import Product  # noqa: E402
from companies.models import Company  # noqa: E402
from shipments.models import Shipment  # noqa: E402
from users.models import OperatorInvite, User  # noqa: E402

from browser import Browser  # noqa: E402
from e2e import borrar_historial, check, summary  # noqa: E402

PYTHON = os.path.join(BASE_DIR, "venv", "Scripts", "python.exe")
FRONT = "http://localhost:5173"
API = "http://127.0.0.1:8000/api"
TAG = "SMOKE103"
# Un token con forma de UUID que no existe: sirve para el 404 del receptor.
TOKEN_FANTASMA = "00000000-0000-0000-0000-000000000000"

procesos = [
    subprocess.Popen([PYTHON, "manage.py", "runserver", "127.0.0.1:8000", "--noreload"],
                     cwd=BASE_DIR, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL),
    subprocess.Popen(["npm.cmd", "run", "dev"], cwd=os.path.join(BASE_DIR, "frontend"),
                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL),
]

nav = None
company = None
remito = None
producto = None
try:
    for url in (f"{API}/public/shipment/{TOKEN_FANTASMA}/", FRONT):
        limite = time.time() + 120
        while time.time() < limite:
            try:
                requests.get(url, timeout=5)
                break
            except Exception:
                time.sleep(0.5)
        else:
            raise RuntimeError(f"no levantó {url}")

    # --- Datos: una empresa recién creada, sin nada adentro -----------------
    print("=== 0. Una empresa recién creada, sin remitos ni productos ===")
    company = Company.objects.create(name=f"Acopio {TAG} SRL",
                                     email=f"{TAG.lower()}@friese.test")
    op_pass = secrets.token_urlsafe(18)
    operador = User.objects.create_user(
        username=f"{TAG.lower()}_op", password=op_pass, company=company,
        role=User.OPERATOR, email=f"{TAG.lower()}op@friese.test")
    invite = OperatorInvite.objects.create(
        company=company, expires_at=timezone.now() + timedelta(days=7))
    check(company.shipments.count() == 0 and company.products.count() == 0,
          "la empresa arranca sin un solo remito ni producto")

    nav = Browser()  # 390x844: la app del operador es mobile-first (diseno.md 5)

    def texto_de_la_pantalla():
        return (nav.js("document.body.innerText") or "").strip()

    def pantalla_no_vacia(ruta, espera, label):
        """Abre una ruta y confirma que dice algo. El criterio de la tarea es
        literal: ninguna pantalla puede quedar en blanco."""
        nav.goto(f"{FRONT}{ruta}")
        nav.wait(espera, label=ruta)
        texto = texto_de_la_pantalla()
        check(len(texto) > 40, f"{label} no queda en blanco",
              f"{len(texto)} caracteres: {texto.splitlines()[0][:60]}")
        return texto

    # --- 1. Rutas públicas, sin sesión -------------------------------------
    print("\n=== 1. Las pantallas públicas dicen algo ===")
    pantalla_no_vacia("/login", "document.querySelector('#username')", "el login")
    pantalla_no_vacia("/recuperar-contrasena", "document.querySelector('form')",
                      "recuperar contraseña")
    pantalla_no_vacia(f"/restablecer/{invite.token}/abc-123",
                      "document.querySelector('form') || document.body.innerText.length > 40",
                      "restablecer contraseña")
    pantalla_no_vacia(f"/alta-operador/{invite.token}",
                      "document.querySelector('#username')", "el alta por QR")

    texto = pantalla_no_vacia(f"/remito/{TOKEN_FANTASMA}",
                              "document.querySelector('[data-testid=load-error]')",
                              "el link del receptor que no existe")
    check("No encontramos este remito" in texto and "email" in texto,
          "y explica qué hacer con un link incompleto", texto.splitlines()[0][:60])

    # --- 2. La lista de remitos vacía --------------------------------------
    print("\n=== 2. La lista de remitos, sin un solo remito ===")
    nav.goto(f"{FRONT}/login")
    nav.wait("document.querySelector('#username')", label="login")
    nav.fill("#username", f"{TAG.lower()}_op")
    nav.fill("#password", op_pass)
    nav.click("button[type=submit]")
    nav.wait("location.pathname === '/'", timeout=60, label="entra a la lista")

    nav.wait("document.querySelector('[data-testid=empty-shipments]')",
             label="estado vacío de la lista")
    vacio = nav.text("[data-testid=empty-shipments]")
    check("Todavía no hay remitos" in vacio,
          "CRITERIO — la lista vacía explica que todavía no hay remitos", vacio[:70])
    check(nav.js(
        "!!Array.from(document.querySelectorAll('[data-testid=empty-shipments] a'))"
        ".find((a) => a.getAttribute('href') === '/remitos/nuevo')"),
        "y ofrece el botón para crear el primero")
    nav.shot("e01-lista-vacia")

    nav.click_js(
        "Array.from(document.querySelectorAll('[data-testid=empty-shipments] a'))"
        ".find((a) => a.getAttribute('href') === '/remitos/nuevo')",
        label="botón «Creá el primero»")
    nav.wait("location.pathname === '/remitos/nuevo'", label="alta de remito")
    check(True, "y el botón lleva de verdad al alta de remito")

    # --- 3. El alta de remito con el catálogo vacío -------------------------
    print("\n=== 3. El alta de remito, sin productos cargados ===")
    nav.wait("document.querySelector('[data-testid=empty-products]')",
             label="estado vacío del catálogo")
    vacio = nav.text("[data-testid=empty-products]")
    check("todavía no tiene productos" in vacio,
          "CRITERIO — el catálogo vacío se explica", vacio[:70])
    check("admin" in vacio and "borrador" in vacio,
          "y dice quién los carga y que el remito se puede guardar igual", vacio[:120])
    check(nav.js("document.querySelectorAll('[data-testid=empty-products] button').length") == 1,
          "con el botón para releer la lista")
    nav.shot("e02-alta-sin-productos")

    # El botón sirve de verdad: se carga un producto y se refresca sin recargar.
    producto = Product.objects.create(company=company, name=f"Maíz {TAG}", unit="ton")
    nav.click("[data-testid=empty-products] button")
    nav.wait("document.querySelector('#product-search')", label="catálogo recargado")
    check(not nav.js("!!document.querySelector('[data-testid=empty-products]')"),
          "y al tocarlo aparece el producto recién cargado, sin recargar la página")

    vacio = nav.text("[data-testid=empty-items]")
    check("Todavía no agregaste productos" in vacio,
          "la lista de productos del remito, vacía, también se explica", vacio[:70])

    nav.fill("#product-search", "no-existe-este-producto")
    nav.wait("document.querySelector('[data-testid=empty-search]')", label="búsqueda sin resultados")
    check("Ningún producto coincide" in nav.text("[data-testid=empty-search]"),
          "una búsqueda sin resultados explica que no hay coincidencias")
    nav.shot("e03-busqueda-sin-resultados")
    nav.click("[data-testid=empty-search] button")
    nav.wait("!document.querySelector('[data-testid=empty-search]')",
             label="búsqueda borrada")
    check(nav.js("document.querySelector('#product-search').value") == "",
          "y el botón «Borrar la búsqueda» devuelve el catálogo completo")

    # --- 4. El detalle de un remito sin productos ni fotos ------------------
    print("\n=== 4. El detalle de un remito vacío ===")
    remito = Shipment.objects.create(company=company, operator=operador,
                                     receiver_name=f"Corralón {TAG}")
    nav.goto(f"{FRONT}/remitos/{remito.pk}")
    nav.wait("document.querySelector('[data-testid=empty-items]')", label="detalle del remito")
    vacio = nav.text("[data-testid=empty-items]")
    check("no tiene productos" in vacio and "despacharlo igual" in vacio,
          "CRITERIO — un remito sin productos explica que se puede despachar igual",
          vacio[:80])
    texto = texto_de_la_pantalla()
    check("Todavía no sacaste fotos" in texto,
          "y la sección de fotos vacía dice que todavía no se sacó ninguna")
    check(nav.js("!!document.querySelector('[data-testid=open-camera]')"),
          "con el botón de sacar la primera foto a la vista")
    nav.shot("e04-detalle-vacio")

    # --- 5. La lista filtrada sin resultados -------------------------------
    print("\n=== 5. Un filtro que no deja nada a la vista ===")
    nav.goto(f"{FRONT}/")
    nav.wait("document.querySelector('[data-testid=empty-shipments]') || "
             "document.querySelector('ul')", label="lista con el remito")
    nav.click_js(
        "Array.from(document.querySelectorAll('button')).find((b) => b.textContent.trim() === 'Aceptado')",
        label="filtro Aceptado")
    nav.wait("document.querySelector('[data-testid=empty-filter]')", label="filtro sin resultados")
    vacio = nav.text("[data-testid=empty-filter]")
    check("No hay remitos en estado" in vacio and "Aceptado" in vacio,
          "el filtro sin resultados dice de qué estado se trata", vacio[:70])
    nav.shot("e05-filtro-vacio")
    nav.click_js(
        "Array.from(document.querySelectorAll('[data-testid=empty-filter] button'))[0]",
        label="botón «Ver todos»")
    nav.wait("!document.querySelector('[data-testid=empty-filter]')", label="filtro limpio")
    check(nav.js(
        "Array.from(document.querySelectorAll('a')).filter("
        "(a) => /^\\/remitos\\/\\d+$/.test(a.getAttribute('href') || '')).length") == 1,
        "y «Ver todos» devuelve la lista completa")

    # --- 6. Barrido final: ninguna ruta en blanco --------------------------
    print("\n=== 6. Barrido: ninguna ruta de la app queda en blanco ===")
    rutas = ["/", "/remitos/nuevo", f"/remitos/{remito.pk}", "/remitos/999999999",
             f"/remito/{TOKEN_FANTASMA}", "/ruta-que-no-existe"]
    for ruta in rutas:
        nav.goto(f"{FRONT}{ruta}")
        nav.wait("document.body.innerText.trim().length > 40", label=f"contenido de {ruta}")
        texto = texto_de_la_pantalla()
        check(len(texto) > 40, f"«{ruta}» muestra contenido",
              f"{len(texto)} caracteres: {texto.splitlines()[0][:50]}")
    # Los 404 son los que provocan las dos rutas inventadas de arriba (el remito y el
    # link del receptor que no existen): son justamente los que disparan la pantalla
    # de error, así que no cuentan. Cualquier OTRO error de consola sí.
    otros_errores = [e for e in nav.errores_de_consola() if "404" not in e]
    check(not otros_errores, "y el recorrido no dejó ningún error de consola inesperado",
          " | ".join(otros_errores)[:120])
finally:
    ids_remitos = [remito.pk] if remito else []
    ids_usuarios = list(User.objects.filter(username__startswith=TAG.lower())
                        .values_list("pk", flat=True))
    Shipment.objects.filter(pk__in=ids_remitos).delete()
    if producto:
        Product.objects.filter(pk=producto.pk).delete()
    if company:
        OperatorInvite.objects.filter(company=company).delete()
        User.objects.filter(company=company).delete()
        ids_empresas = [company.pk]
        Company.objects.filter(pk=company.pk).delete()
    else:
        ids_empresas = []
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
sys.exit(summary("estados vacíos (10.3)"))
