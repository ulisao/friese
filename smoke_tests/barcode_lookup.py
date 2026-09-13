"""Tarea 11.2 — Smoke test EN PRODUCCIÓN de GET /api/products/by-barcode/.

Crea su propia empresa, producto y operador (marca SMOKE112) y los borra al
final, igual que prod_verify.py. Verifica:

  1. Un código conocido devuelve el producto correcto.
  2. Un código inexistente devuelve 404 con un mensaje claro.
  3. El operador de otra empresa no puede leer el producto por su código
     (aislamiento multi-tenant, sección 2.2).
"""

import os
import secrets
import sys

import django

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE_DIR)
sys.path.insert(0, HERE)
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
django.setup()

from django.contrib.auth.hashers import make_password  # noqa: E402

import requests  # noqa: E402

from catalog.models import Product  # noqa: E402
from companies.models import Company  # noqa: E402
from users.models import User  # noqa: E402

from e2e import API, check, summary  # noqa: E402

TAG = "SMOKE112"
CODE = f"{TAG}-CODE-001"

company = otra_company = operador = otro_operador = producto = None
try:
    company = Company.objects.create(name=f"Cargas {TAG} SA", email=f"{TAG.lower()}@friese.test")
    producto = Product.objects.create(
        company=company, name=f"Soja {TAG}", unit="ton", barcode=CODE)

    op_pass = secrets.token_urlsafe(18)
    operador = User.objects.create(
        username=f"{TAG.lower()}_op", password=make_password(op_pass),
        company=company, role=User.OPERATOR, is_active=True)

    otra_company = Company.objects.create(
        name=f"Otra {TAG} SA", email=f"otra{TAG.lower()}@friese.test")
    otro_pass = secrets.token_urlsafe(18)
    otro_operador = User.objects.create(
        username=f"{TAG.lower()}_otro_op", password=make_password(otro_pass),
        company=otra_company, role=User.OPERATOR, is_active=True)

    def login(username, password):
        token = requests.post(f"{API}/auth/login/", json={
            "username": username, "password": password}, timeout=30).json()["access"]
        return {"Authorization": f"Bearer {token}"}

    auth = login(operador.username, op_pass)
    auth_otro = login(otro_operador.username, otro_pass)

    # --- 1. Código conocido -------------------------------------------------
    r = requests.get(f"{API}/products/by-barcode/", headers=auth,
                     params={"code": CODE}, timeout=30)
    check(r.status_code == 200, "código conocido devuelve 200", f"HTTP {r.status_code}")
    body = r.json() if r.status_code == 200 else {}
    check(body.get("id") == producto.id, "devuelve el producto correcto", body)

    # --- 2. Código inexistente ----------------------------------------------
    r = requests.get(f"{API}/products/by-barcode/", headers=auth,
                     params={"code": f"{TAG}-NO-EXISTE"}, timeout=30)
    check(r.status_code == 404, "código inexistente devuelve 404", f"HTTP {r.status_code}")

    # --- 3. Aislamiento multi-tenant -----------------------------------------
    r = requests.get(f"{API}/products/by-barcode/", headers=auth_otro,
                     params={"code": CODE}, timeout=30)
    check(r.status_code == 404,
          "un operador de otra empresa no ve el producto por su código",
          f"HTTP {r.status_code}")
finally:
    if operador:
        User.objects.filter(pk=operador.pk).delete()
    if otro_operador:
        User.objects.filter(pk=otro_operador.pk).delete()
    if producto:
        Product.objects.filter(pk=producto.pk).delete()
    if company:
        Company.objects.filter(pk=company.pk).delete()
    if otra_company:
        Company.objects.filter(pk=otra_company.pk).delete()

sys.exit(summary("tarea 11.2 — GET /api/products/by-barcode/"))
