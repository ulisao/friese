"""Criterio de aceptación de la 10.4 — páginas de error con la marca.

Una URL inexistente tiene que mostrar una página de Friese, no la genérica de Django
ni una pantalla en blanco. Se prueban las tres: el 404 y el 500 del backend y el 404
del frontend.

    python smoke_tests/error_pages.py

El backend se levanta con **DEBUG=False** (sigue en ambiente `development`, así que no
fuerza HTTPS): con DEBUG prendido Django muestra su propia pantalla amarilla de debug y
ni mira los handlers, así que sin esto no se estaría probando nada. El frontend es el
Vite de siempre en :5173. No crea ni borra datos: ninguna de estas pantallas los toca.
"""

import os
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

from django.conf import settings  # noqa: E402
from django.test import RequestFactory  # noqa: E402
from django.urls import get_resolver  # noqa: E402

from config.errors import server_error  # noqa: E402

from browser import Browser  # noqa: E402
from e2e import check, summary  # noqa: E402

PYTHON = os.path.join(BASE_DIR, "venv", "Scripts", "python.exe")
# El 8000 es el que proxea el Vite (frontend/vite.config.js): la pantalla del
# receptor consume la API por el mismo origen, así que el backend de esta corrida
# tiene que ser ESE, o el frontend queda sin API.
PUERTO = 8000
LOCAL = f"http://127.0.0.1:{PUERTO}"
FRONT = "http://localhost:5173"
SOPORTE = settings.SUPPORT_CONTACT_EMAIL

entorno = {**os.environ, "DEBUG": "False"}
procesos = [
    subprocess.Popen([PYTHON, "manage.py", "runserver", f"127.0.0.1:{PUERTO}", "--noreload"],
                     cwd=BASE_DIR, env=entorno,
                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL),
    subprocess.Popen(["npm.cmd", "run", "dev"], cwd=os.path.join(BASE_DIR, "frontend"),
                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL),
]

nav = None
try:
    for url in (f"{LOCAL}/admin/login/", FRONT):
        limite = time.time() + 120
        while time.time() < limite:
            try:
                requests.get(url, timeout=5)
                break
            except Exception:
                time.sleep(0.5)
        else:
            raise RuntimeError(f"no levantó {url}")

    # --- 0. El server de prueba está en el modo que corresponde ------------
    print("=== 0. El backend corre con DEBUG apagado ===")
    r = requests.get(f"{LOCAL}/ruta-que-no-existe/", timeout=30)
    check(r.status_code == 404, "una URL inventada devuelve 404", f"HTTP {r.status_code}")
    check("Traceback" not in r.text and "URLconf" not in r.text,
          "y no es la pantalla de debug de Django (si no, el test no probaría nada)")

    # --- 1. El 404 del backend --------------------------------------------
    print("\n=== 1. El 404 del backend ===")
    html = r.text
    check("Friese" in html and "ERROR 404" in html,
          "CRITERIO — la página lleva la marca de Friese y dice el código")
    check("Esta página no existe" in html, "con un título en castellano")
    check("Not Found" not in html or "Esta página no existe" in html,
          "y no es la página pelada de Django")
    check(SOPORTE in html and f"mailto:{SOPORTE}" in html,
          "trae el contacto de soporte, clickeable (tarea 7.7)", SOPORTE)
    check(settings.FRONTEND_PUBLIC_URL.rstrip("/") in html and 'href="/admin/"' in html,
          "y los dos links para volver: la app y el panel")
    check("#1a1a22" in html.lower() and "#d6ac31" in html.lower(),
          "con la paleta de docs/diseno.md (fondo base y dorado de marca)")
    check("<link" not in html and "<script" not in html,
          "sin un solo archivo estático: la página no depende de nada más para verse")

    # El panel tiene su propio catch-all y está detrás del login: a quien no entró,
    # una URL inventada lo manda a la pantalla de login (comportamiento nativo del
    # admin, anterior a esta tarea). Se fija acá para que quede claro que el 404 de
    # Friese no lo pisa.
    r_admin = requests.get(f"{LOCAL}/admin/no-existe-esta-seccion/", timeout=30,
                           allow_redirects=False)
    check(r_admin.status_code == 302 and "/admin/login/" in r_admin.headers.get("Location", ""),
          "una URL inventada del panel sigue yendo al login del panel, como siempre",
          f"HTTP {r_admin.status_code} {r_admin.headers.get('Location', '')}")

    r_api = requests.get(f"{LOCAL}/api/no-existe/", timeout=30)
    check(r_api.status_code == 404 and "ERROR 404" in r_api.text,
          "y una ruta inventada bajo /api/ también", f"HTTP {r_api.status_code}")

    # --- 2. El 500 del backend --------------------------------------------
    print("\n=== 2. El 500 del backend ===")
    resolver = get_resolver()
    check(resolver.resolve_error_handler(404).__module__ == "config.errors"
          and resolver.resolve_error_handler(500).__module__ == "config.errors",
          "Django resuelve los dos handlers a los de Friese",
          resolver.resolve_error_handler(500).__qualname__)

    # No se rompe un endpoint real para probarlo: se invoca el MISMO handler que
    # Django llama ante una excepción, con una request real.
    respuesta = server_error(RequestFactory().get("/lo-que-sea/"))
    cuerpo = respuesta.content.decode()
    check(respuesta.status_code == 500, "el handler responde 500", str(respuesta.status_code))
    check("Friese" in cuerpo and "ERROR 500" in cuerpo and "Se nos rompió algo" in cuerpo,
          "CRITERIO — con la marca y un mensaje en castellano")
    check(SOPORTE in cuerpo and settings.FRONTEND_PUBLIC_URL.rstrip("/") in cuerpo,
          "el contacto de soporte y el link para volver también están en el 500")
    check("Traceback" not in cuerpo and "Exception" not in cuerpo,
          "y no filtra nada del error: el detalle va al log, no a la pantalla")

    # --- 3. El 404 del frontend -------------------------------------------
    print("\n=== 3. El 404 del frontend ===")
    nav = Browser()
    nav.goto(f"{FRONT}/una-ruta-que-no-existe")
    nav.wait("document.querySelector('[data-testid=notfound-message]')", label="404 del frontend")
    check(nav.js("location.pathname") == "/una-ruta-que-no-existe",
          "CRITERIO — la ruta inválida ya no redirige en silencio a la lista",
          nav.js("location.pathname"))
    texto = nav.text("body")
    check("Esta página no existe" in texto and "ERROR 404" in texto,
          "muestra el 404 con la marca", texto.splitlines()[0][:60])
    check(SOPORTE in texto, "con el contacto de soporte a la vista")
    check(nav.js(
        "!!Array.from(document.querySelectorAll('a')).find("
        "(a) => a.getAttribute('href') === '/')"),
        "y el link para volver al inicio")
    nav.shot("x01-404-frontend")

    nav.click_js(
        "Array.from(document.querySelectorAll('a')).find((a) => a.getAttribute('href') === '/')",
        label="botón «Volver al inicio»")
    nav.wait("location.pathname === '/' || location.pathname === '/login'",
             label="vuelta al inicio")
    check(True, "que lleva de verdad al inicio (login si no hay sesión)",
          nav.js("location.pathname"))

    # Una ruta del receptor mal copiada NO cae en el 404 genérico: la maneja su
    # propia pantalla, que sabe explicar lo del link único.
    nav.goto(f"{FRONT}/remito/00000000-0000-0000-0000-000000000000")
    nav.wait("document.querySelector('[data-testid=load-error]')", label="link del receptor")
    check("No encontramos este remito" in nav.text("body"),
          "y el link del receptor que no existe sigue con su propia pantalla, más específica")

    # --- 4. Las capturas del backend --------------------------------------
    print("\n=== 4. Cómo se ven las páginas del backend ===")
    nav.send("Emulation.setDeviceMetricsOverride", {
        "width": 1280, "height": 800, "deviceScaleFactor": 1, "mobile": False})
    nav.goto(f"{LOCAL}/ruta-que-no-existe/")
    nav.wait("document.body.innerText.includes('ERROR 404')", label="404 del backend")
    fondo = nav.js("getComputedStyle(document.body).backgroundColor")
    check(fondo.replace(" ", "") == "rgb(26,26,34)",
          "el 404 del backend se dibuja sobre el fondo oscuro de la marca", fondo)
    nav.shot("x02-404-backend")

    # El 500 no se puede provocar sin romper algo: se mira el HTML del handler.
    quinientos = os.path.join(HERE, "shots", "x03-500-backend.html")
    with open(quinientos, "w", encoding="utf-8") as fh:
        fh.write(cuerpo)
    nav.goto("file:///" + quinientos.replace("\\", "/"))
    nav.wait("document.body.innerText.includes('ERROR 500')", label="500 renderizado")
    check(nav.js("getComputedStyle(document.body).backgroundColor").replace(" ", "")
          == "rgb(26,26,34)", "y el 500 se ve igual")
    nav.shot("x03-500-backend")
    os.remove(quinientos)

    check(not [e for e in nav.errores_de_consola() if "404" not in e],
          "ninguna de las pantallas tira errores de consola inesperados")
finally:
    if nav:
        nav.close()
    for proceso in procesos:
        proceso.terminate()
        try:
            proceso.wait(timeout=10)
        except Exception:
            proceso.kill()

sys.exit(summary("páginas de error (10.4)"))
