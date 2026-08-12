"""Fase 6.6 — chequeos de hardening (tarea 6.2) contra el backend REAL de producción."""

import concurrent.futures
import os
import sys

import django
import requests

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE_DIR)
sys.path.insert(0, HERE)
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
django.setup()

from e2e import API, BACKEND, FRONTEND, check, summary  # noqa: E402

TOKEN_INEXISTENTE = "00000000-0000-0000-0000-000000000000"
PUBLICO = f"{API}/public/shipment/{TOKEN_INEXISTENTE}/"

# --- HTTPS forzado y headers ------------------------------------------------
r = requests.get(BACKEND.replace("https://", "http://") + "/admin/login/",
                 allow_redirects=False, timeout=30)
check(r.status_code in (301, 302) and r.headers.get("Location", "").startswith("https://"),
      "producción redirige http -> https", f"HTTP {r.status_code} {r.headers.get('Location')}")

r = requests.get(f"{BACKEND}/admin/login/", timeout=30)
h = {k.lower(): v for k, v in r.headers.items()}
check("max-age=31536000" in h.get("strict-transport-security", ""),
      "HSTS de 1 año", h.get("strict-transport-security"))
check("includeSubDomains" in h.get("strict-transport-security", ""), "HSTS con includeSubDomains")
check(h.get("x-content-type-options") == "nosniff", "X-Content-Type-Options: nosniff")
check(h.get("x-frame-options") == "DENY", "X-Frame-Options: DENY")
check(h.get("referrer-policy") == "same-origin", "Referrer-Policy: same-origin")
check(h.get("cross-origin-opener-policy") == "same-origin", "COOP: same-origin")
check("Secure" in r.headers.get("Set-Cookie", ""), "la cookie de CSRF sale con Secure")
check("DEBUG" not in requests.get(f"{BACKEND}/ruta-que-no-existe/", timeout=30).text,
      "un 404 no filtra el traceback de debug")

# --- CORS -------------------------------------------------------------------
r = requests.options(f"{API}/auth/login/", timeout=30, headers={
    "Origin": FRONTEND, "Access-Control-Request-Method": "POST",
    "Access-Control-Request-Headers": "content-type"})
check(r.headers.get("access-control-allow-origin") == FRONTEND,
      "el frontend de producción está permitido por CORS")
r = requests.options(f"{API}/auth/login/", timeout=30, headers={
    "Origin": "https://sitio-cualquiera.com", "Access-Control-Request-Method": "POST"})
check("access-control-allow-origin" not in {k.lower() for k in r.headers},
      "un origen ajeno NO recibe permiso de CORS")

# --- Rate limiting de /api/public/ -----------------------------------------
def pegar(_, headers=None):
    return requests.get(PUBLICO, headers=headers or {}, timeout=30).status_code


with concurrent.futures.ThreadPoolExecutor(max_workers=12) as pool:
    codigos = list(pool.map(pegar, range(45)))

check(429 in codigos, "el endpoint público corta con 429 ante un volumen anormal",
      f"{codigos.count(404)} x 404, {codigos.count(429)} x 429")
check(codigos.count(404) <= 31,
      "el corte llega en el orden de las 30 requests por minuto configuradas",
      f"{codigos.count(404)} pasaron")

r = requests.get(PUBLICO, timeout=30)
check(r.status_code == 429 and "Retry-After" in r.headers,
      "el 429 trae Retry-After", r.headers.get("Retry-After"))

# Con el cupo agotado, un X-Forwarded-For inventado no puede resetear el contador:
# si lo reseteara, cualquiera saltearía el límite con un header.
r = requests.get(PUBLICO, headers={"X-Forwarded-For": "203.0.113.77"}, timeout=30)
check(r.status_code == 429,
      "un X-Forwarded-For falso NO resetea el cupo (NUM_PROXIES correcto)",
      f"HTTP {r.status_code}")

# El operador autenticado y el admin no quedan limitados por el cupo público.
check(requests.get(f"{API}/shipments/", timeout=30).status_code == 401,
      "la API del operador sigue respondiendo 401 (no 429): el cupo es solo del público")
check(requests.get(f"{BACKEND}/admin/login/", timeout=30).status_code == 200,
      "el Django Admin no quedó limitado por el cupo público")

sys.exit(summary("hardening en producción"))
