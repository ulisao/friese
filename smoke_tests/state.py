"""Fase 6.6 — foto del estado actual de la base (solo lectura)."""

import os
import sys

import django

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
django.setup()

from catalog.models import Product  # noqa: E402
from companies.models import Company, UsageLog  # noqa: E402
from shipments.models import Evidence, Shipment  # noqa: E402
from users.models import OperatorInvite, User  # noqa: E402

print("COMPANIES:", Company.objects.count())
for c in Company.objects.all():
    print("  -", c.id, c.name, "| trial:", c.trial_shipments_remaining,
          "| activa:", c.is_active, "| email:", c.email)

print("USERS:", User.objects.count())
for u in User.objects.all():
    print("  -", u.id, u.username, "| role:", u.role, "| company:", u.company_id,
          "| super:", u.is_superuser, "| staff:", u.is_staff, "| email:", u.email)

print("PRODUCTS:", Product.objects.count())
for p in Product.objects.all()[:20]:
    print("  -", p.id, p.name, p.unit, "| company:", p.company_id, "| activo:", p.is_active)

print("INVITES:", OperatorInvite.objects.count())

print("SHIPMENTS:", Shipment.objects.count())
for s in Shipment.objects.all()[:20]:
    print("  -", s.id, s.status, "| token:", s.public_token, "| opened:", s.link_opened_at,
          "| company:", s.company_id)

print("EVIDENCE:", Evidence.objects.count())
print("USAGELOG:", list(UsageLog.objects.values("company_id", "month", "shipments_created",
                                                "photos_uploaded", "emails_sent")))
