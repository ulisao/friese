"""Fase 6.6 — ¿el cache en la base cuenta bien, o la concurrencia se le escapa?

El throttle de DRF hace read-modify-write sobre el cache: lee la lista de
timestamps, le agrega uno y la vuelve a escribir, SIN lock. Con el cache en
memoria del proceso esa ventana dura microsegundos y no se nota. Contra una base
remota (Supabase) dura lo que tarde el viaje de ida y vuelta, y varias requests
simultáneas pueden leer todas la misma lista vieja y pisarse.

Este script mide dónde corta el límite con distintos niveles de concurrencia
contra UN SOLO proceso, para separar ese efecto del de los workers.
"""

import concurrent.futures
import os
import subprocess
import sys
import time
from collections import Counter

import django
import requests

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE_DIR)
sys.path.insert(0, HERE)
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
django.setup()

from django.core.cache import cache  # noqa: E402

PYTHON = os.path.join(BASE_DIR, "venv", "Scripts", "python.exe")
PUERTO = 8013
URL = f"http://127.0.0.1:{PUERTO}/api/public/shipment/00000000-0000-0000-0000-000000000000/"
CLAVE = "throttle_public_burst_127.0.0.1"

proc = subprocess.Popen([PYTHON, "manage.py", "runserver", f"127.0.0.1:{PUERTO}", "--noreload"],
                        cwd=BASE_DIR, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def pegar(_):
    return requests.get(URL, timeout=30).status_code


try:
    limite = time.time() + 60
    while time.time() < limite:
        try:
            requests.get(URL, timeout=5)
            break
        except Exception:
            time.sleep(0.4)

    print(f"{'concurrencia':>12} | {'pasaron':>7} | {'429':>4} | {'segundos':>8} | "
          f"{'timestamps guardados':>20}")
    print("-" * 70)
    for concurrencia in (1, 2, 5, 10):
        cache.clear()
        arranque = time.time()
        with concurrent.futures.ThreadPoolExecutor(max_workers=concurrencia) as pool:
            codigos = list(pool.map(pegar, range(45)))
        tardo = time.time() - arranque
        conteo = Counter(codigos)
        guardados = len(cache.get(CLAVE) or [])
        print(f"{concurrencia:>12} | {conteo.get(404, 0):>7} | {conteo.get(429, 0):>4} | "
              f"{tardo:>8.1f} | {guardados:>20}")
finally:
    proc.terminate()
    try:
        proc.wait(timeout=10)
    except Exception:
        proc.kill()
