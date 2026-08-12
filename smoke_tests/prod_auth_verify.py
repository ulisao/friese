"""Verificación EN PRODUCCIÓN de la 6.7, ya con api.friese.com.ar.

Lo que agrega sobre la prueba local: la cookie viaja entre DOS ORÍGENES distintos
del mismo sitio (app.friese.com.ar -> api.friese.com.ar), que es la situación real
y la que obligó a configurar el subdominio. Acá se ve si el CORS con credenciales,
el SameSite y el Secure están bien de verdad.

Crea sus datos con la marca SMOKE71 y los borra al final.
"""

import os
import secrets
import sys

import django
import requests

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE_DIR)
sys.path.insert(0, HERE)
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
django.setup()

from django.conf import settings  # noqa: E402

from catalog.models import Product  # noqa: E402
from companies.models import Company  # noqa: E402
from shipments.models import Evidence, Shipment  # noqa: E402
from users.models import OperatorInvite, User  # noqa: E402

from browser import Browser  # noqa: E402
from e2e import API, BACKEND, FRONTEND, check, summary  # noqa: E402

TAG = "SMOKE71"
company = navegador = None
try:
    company = Company.objects.create(name=f"Auth {TAG} SA", email=f"{TAG.lower()}@friese.test")
    Product.objects.create(company=company, name=f"Urea {TAG}", unit="ton")
    op_user, op_pass = f"{TAG.lower()}_op", secrets.token_urlsafe(18)
    User.objects.create_user(username=op_user, password=op_pass, company=company,
                             role=User.OPERATOR)

    # --- 1. CORS con credenciales entre los dos subdominios ---------------
    r = requests.options(f"{API}/auth/login/", timeout=30, headers={
        "Origin": FRONTEND, "Access-Control-Request-Method": "POST",
        "Access-Control-Request-Headers": "content-type"})
    check(r.headers.get("access-control-allow-origin") == FRONTEND,
          "el preflight autoriza al frontend")
    check(r.headers.get("access-control-allow-credentials") == "true",
          "el preflight permite mandar credenciales (sin esto el navegador tira la cookie)",
          r.headers.get("access-control-allow-credentials"))

    # --- 2. La cookie, en el dominio real --------------------------------
    sesion = requests.Session()
    r = sesion.post(f"{API}/auth/login/", json={"username": op_user, "password": op_pass},
                    timeout=30, headers={"Origin": FRONTEND})
    check(r.status_code == 200 and "access" in r.json(), "login en producción")
    check("refresh" not in r.json(), "el refresh NO viene en el cuerpo")
    cookie = r.headers.get("Set-Cookie", "")
    check("HttpOnly" in cookie, "la cookie es HttpOnly")
    check("Secure" in cookie, "la cookie es Secure (en producción sí, a diferencia de dev)")
    check("SameSite=Lax" in cookie, "la cookie es SameSite=Lax")
    check("Path=/api/auth/" in cookie, "la cookie solo viaja a /api/auth/")
    check("Domain=" not in cookie,
          "la cookie es host-only: queda atada a api.friese.com.ar y no se comparte con "
          "cualquier subdominio de friese.com.ar")

    r = sesion.post(f"{API}/auth/refresh/", timeout=30, headers={"Origin": FRONTEND})
    check(r.status_code == 200 and "access" in r.json(),
          "el refresh funciona con la cookie entre subdominios", f"HTTP {r.status_code}")
    r = requests.post(f"{API}/auth/refresh/", timeout=30)
    check(r.status_code == 401, "sin cookie, 401")
    r = sesion.post(f"{API}/auth/logout/", timeout=30, headers={"Origin": FRONTEND})
    check(r.status_code == 205, "logout 205")
    r = sesion.post(f"{API}/auth/refresh/", timeout=30, headers={"Origin": FRONTEND})
    check(r.status_code == 401, "después del logout el refresh queda muerto")

    # --- 3. El operador, en el navegador, contra producción ---------------
    navegador = Browser()
    navegador.goto(f"{FRONTEND}/login")
    navegador.wait("document.querySelector('#username')", label="login")
    navegador.fill("#username", op_user)
    navegador.fill("#password", op_pass)
    navegador.click("button[type=submit]")
    navegador.wait("location.pathname === '/'", timeout=90, label="entra")
    check(True, "el operador entra en producción con la API en el otro subdominio")

    check(settings.REFRESH_COOKIE_NAME not in (navegador.js("document.cookie") or ""),
          "document.cookie no expone el refresh",
          f"«{navegador.js('document.cookie')}»")
    almacen = navegador.js("JSON.stringify(Object.entries(localStorage))")
    check("refresh" not in (almacen or "").lower(),
          "localStorage no guarda ningún refresh", almacen[:100])

    # La prueba de fuego: recargar. El access vive solo en memoria, así que si la
    # sesión sobrevive es porque la cookie cruzó de app. a api. y funcionó.
    navegador.goto(f"{FRONTEND}/")
    navegador.wait("document.querySelector('a[href=\"/remitos/nuevo\"]')", timeout=90,
                   label="sesión revivida")
    check(navegador.js("location.pathname") == "/",
          "recargando, la sesión se revive con la cookie (no vuelve al login)")
    navegador.shot("q01-sesion-revivida-produccion")

    # Y que las llamadas autenticadas anden después de esa revivida.
    navegador.goto(f"{FRONTEND}/remitos/nuevo")
    navegador.wait("document.querySelector('#product-search')", timeout=90, label="catálogo")
    check(True, "el catálogo carga: las llamadas con Bearer siguen funcionando")

    navegador.goto(f"{FRONTEND}/")
    navegador.wait("document.querySelector('a[href=\"/remitos/nuevo\"]')", label="lista")
    navegador.js("[...document.querySelectorAll('button')]"
                 ".find(b => b.innerText.trim() === 'Salir').click()")
    navegador.wait("location.pathname === '/login'", timeout=90, label="logout")
    navegador.goto(f"{FRONTEND}/")
    navegador.wait("location.pathname === '/login'", timeout=90, label="sigue afuera")
    check(True, "el botón Salir cierra la sesión de verdad: ya no revive")
    navegador.shot("q02-logout-produccion")

    errores = [e for e in navegador.errores_de_consola() if "Content Security Policy" in e]
    check(not errores, "ninguna violación de CSP en producción",
          " | ".join(errores)[:200] if errores else "0 violaciones")
finally:
    if navegador:
        navegador.close()
    if company:
        ids = list(Shipment.objects.filter(company=company).values_list("id", flat=True))
        Evidence.objects.filter(shipment_id__in=ids).delete()
        Shipment.objects.filter(company=company).delete()
        Product.objects.filter(company=company).delete()
        OperatorInvite.objects.filter(company=company).delete()
        User.objects.filter(company=company).delete()
        Company.objects.filter(pk=company.pk).delete()

sys.exit(summary("6.7 en producción, con api.friese.com.ar"))
