"""Fase 6.6 — estado de la cuenta de Resend (solo lectura).

Lee la API key del entorno del proyecto (nunca se imprime).
"""

import json
import os
import sys
import urllib.request

import django

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
django.setup()

from django.conf import settings  # noqa: E402

key = settings.RESEND_API_KEY
print("RESEND_FROM_EMAIL (local):", settings.RESEND_FROM_EMAIL)
print("FRONTEND_PUBLIC_URL (local):", settings.FRONTEND_PUBLIC_URL)


def get(path):
    req = urllib.request.Request(
        f"https://api.resend.com{path}",
        headers={
            "Authorization": f"Bearer {key}",
            "User-Agent": "friese-smoke-test/1.0",
            "Accept": "application/json",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return resp.status, json.loads(resp.read().decode())
    except Exception as exc:  # noqa: BLE001
        body = getattr(exc, "read", lambda: b"")()
        return getattr(exc, "code", "ERR"), body.decode(errors="replace") or str(exc)


status, domains = get("/domains")
print("\nGET /domains ->", status)
print(json.dumps(domains, indent=2, ensure_ascii=False)[:2000])

status, emails = get("/emails")
print("\nGET /emails ->", status)
if isinstance(emails, dict):
    for e in (emails.get("data") or [])[:10]:
        print("  -", e.get("created_at"), "|", e.get("from"), "->", e.get("to"),
              "|", e.get("last_event"), "|", (e.get("subject") or "")[:70])
else:
    print(str(emails)[:500])
