"""Fase 6.6 — recheck del aislamiento multi-tenant contra el admin de producción."""

import json
import os
import sys

import django

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BASE_DIR)
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
django.setup()

from companies.models import Company  # noqa: E402

from e2e import BACKEND, admin_login  # noqa: E402

with open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "state.json"),
          encoding="utf-8") as fh:
    state = json.load(fh)

s, r = admin_login(state["admin_username"], state["admin_password"])
print("login del admin de empresa:", r.status_code)

otra = Company.objects.exclude(pk=state["company_id"]).first()
print("empresa ajena:", otra.pk, otra.name)

for label, path in (
    ("ficha de la empresa ajena", f"/admin/companies/company/{otra.pk}/change/"),
    ("listado de empresas", "/admin/companies/company/"),
    ("listado de remitos", "/admin/shipments/shipment/"),
    ("listado de usuarios", "/admin/users/user/"),
    ("listado de productos", "/admin/catalog/product/"),
):
    resp = s.get(f"{BACKEND}{path}", allow_redirects=False, timeout=30)
    loc = resp.headers.get("Location", "")
    body = resp.text if resp.status_code == 200 else ""
    leaks = [name for name in Company.objects.exclude(pk=state["company_id"])
             .values_list("name", flat=True) if name in body]
    print(f"\n{label}: HTTP {resp.status_code} {loc}")
    print("   ¿aparece el nombre de otra empresa en el HTML?:", leaks or "no")
