"""Fase 6.6 — ¿el contador del rate limit quedó COMPARTIDO entre procesos?

Levanta DOS servidores Django (dos procesos, como los workers de gunicorn en
producción) contra la misma base y reparte las requests entre los dos. Con el
cache en memoria cada proceso contaba por su cuenta y pasaban 2 x 30; con el
cache en la base tiene que cortar en 30 en total, sin importar a qué proceso le
toque cada request.
"""

import concurrent.futures
import itertools
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

from e2e import check, summary  # noqa: E402

PYTHON = os.path.join(BASE_DIR, "venv", "Scripts", "python.exe")
PUERTOS = (8011, 8012)
TOKEN = "00000000-0000-0000-0000-000000000000"

# Arranca de cero: si quedó un contador de una corrida anterior, el corte no cae
# donde corresponde y el resultado no diría nada.
cache.clear()

procesos = [
    subprocess.Popen([PYTHON, "manage.py", "runserver", f"127.0.0.1:{p}", "--noreload"],
                     cwd=BASE_DIR, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    for p in PUERTOS
]

try:
    for p in PUERTOS:
        limite = time.time() + 60
        while time.time() < limite:
            try:
                requests.get(f"http://127.0.0.1:{p}/api/public/shipment/{TOKEN}/", timeout=5)
                break
            except Exception:
                time.sleep(0.4)
        else:
            raise RuntimeError(f"el server de :{p} no levantó")
    # El ping de arranque ya consumió una request por servidor.
    cache.clear()

    # EN PARALELO, repartidas entre los dos procesos. En serie no sirve: la ventana
    # de DRF es deslizante y cada request tarda lo suyo contra Supabase, así que
    # 40 requests seguidas nunca llegan a llenar el minuto (ya anotado en la 6.2).
    turnos = itertools.cycle(PUERTOS)
    objetivos = [next(turnos) for _ in range(80)]

    def pegar(puerto):
        r = requests.get(f"http://127.0.0.1:{puerto}/api/public/shipment/{TOKEN}/", timeout=30)
        return puerto, r.status_code

    arranque = time.time()
    with concurrent.futures.ThreadPoolExecutor(max_workers=10) as pool:
        codigos = list(pool.map(pegar, objetivos))
    print(f"  80 requests en paralelo entre 2 procesos, en {time.time() - arranque:.1f}s:",
          dict(Counter(c for _, c in codigos)))

    pasaron = Counter(c for _, c in codigos).get(404, 0)
    # Con el cache en memoria pasaban 2 x 30 = 60. Con el contador compartido tienen
    # que pasar ~30: no exactamente 30 porque el throttle de DRF lee y escribe el
    # contador sin lock, así que dos requests simultáneas pueden colarse.
    check(pasaron <= 40, "el cupo dejó de multiplicarse por la cantidad de procesos",
          f"pasaron {pasaron} (antes pasaban ~60)")
    check(25 <= pasaron <= 40, "el corte cae en el entorno de las 30 configuradas",
          f"pasaron {pasaron}")
    por_proceso = Counter(p for p, c in codigos if c == 404)
    check(len(por_proceso) == 2,
          "los dos procesos atendieron requests dentro del MISMO cupo",
          str(dict(por_proceso)))
    check(any(c == 429 for _, c in codigos), "el resto corta con 429")

    claves = [k for k in ("throttle_public_burst_127.0.0.1", "throttle_public_sustained_127.0.0.1")]
    check(any(cache.get(k) for k in claves),
          "el contador vive en el cache COMPARTIDO (la tabla de la base), no en el proceso")
finally:
    for proc in procesos:
        proc.terminate()
    for proc in procesos:
        try:
            proc.wait(timeout=10)
        except Exception:
            proc.kill()

sys.exit(summary("contador compartido"))
