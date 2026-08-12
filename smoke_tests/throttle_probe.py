"""Fase 6.6 — ¿dónde corta realmente el rate limit del público en producción?

La 6.2 dejó anotado que el contador del throttle vive en el cache LOCAL del proceso.
El servicio de Railway arranca gunicorn con --workers 2, así que la sospecha es que
cada worker lleva su propia cuenta y el cupo efectivo es 30 x cantidad de workers.
"""

import collections
import concurrent.futures
import os
import sys
import time

import requests

BACKEND = "https://friese-production.up.railway.app"
PUBLICO = f"{BACKEND}/api/public/shipment/00000000-0000-0000-0000-000000000000/"

print("Esperando 65s a que se vacíe la ventana del minuto anterior…")
time.sleep(65)


def pegar(_):
    try:
        return requests.get(PUBLICO, timeout=30).status_code
    except Exception as exc:  # noqa: BLE001
        return type(exc).__name__


TOTAL = int(sys.argv[1]) if len(sys.argv) > 1 else 120
CONCURRENCIA = int(sys.argv[2]) if len(sys.argv) > 2 else 16
with concurrent.futures.ThreadPoolExecutor(max_workers=CONCURRENCIA) as pool:
    codigos = list(pool.map(pegar, range(TOTAL)))

print(f"{TOTAL} requests con concurrencia {CONCURRENCIA}:",
      dict(collections.Counter(codigos)))
print("primera 429 en la posición:",
      next((i + 1 for i, c in enumerate(codigos) if c == 429), "nunca"))

r = requests.get(PUBLICO, timeout=30)
print("request siguiente:", r.status_code, "| Retry-After:", r.headers.get("Retry-After"))
