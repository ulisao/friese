"""Fase 6.6 — contenido del aviso de queja al admin (tarea 5.3), tal como salió."""

import json
import os
import sys
import urllib.request

import django

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE_DIR)
sys.path.insert(0, HERE)
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
django.setup()

from django.conf import settings  # noqa: E402

from shipments.models import Evidence, Shipment  # noqa: E402

from e2e import check, summary  # noqa: E402


def get(path):
    req = urllib.request.Request(
        f"https://api.resend.com{path}",
        headers={"Authorization": f"Bearer {settings.RESEND_API_KEY}",
                 "User-Agent": "friese-smoke66/1.0", "Accept": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read().decode())


with open(os.path.join(HERE, "state.json"), encoding="utf-8") as fh:
    state = json.load(fh)

sid = state["shipments"]["B"]["id"]
shipment = Shipment.objects.get(pk=sid)

queja = [e for e in get("/emails")["data"] if "Queja" in (e.get("subject") or "")]
check(bool(queja), "hay un email de queja en Resend")
detail = get(f"/emails/{queja[0]['id']}")
html = detail.get("html") or ""

check(shipment.dispute_reason in html, "el aviso trae el motivo que escribió el receptor")
check(f"#{sid}" in html, "el aviso identifica el remito")
check(shipment.receiver_name in html, "el aviso identifica al receptor")
fotos = list(Evidence.objects.filter(shipment_id=sid, type=Evidence.RECEPTION)
             .values_list("file_url", flat=True))
check(all(u in html for u in fotos),
      f"el aviso incluye las {len(fotos)} fotos de la carga recibida")
print("\n  destinatarios:", detail.get("to"), "| asunto:", detail.get("subject"))
sys.exit(summary("email de queja"))
