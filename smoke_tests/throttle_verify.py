"""Fase 6.6 — verificación limpia del rate limit en producción, con el cache compartido.

Borra los contadores de esta máquina, dispara una ráfaga y mira el resultado por
DOS lados: los códigos que devolvió producción y los timestamps que quedaron
guardados por IP en la tabla de cache.

Ojo con el dato que confunde la lectura: esta conexión sale por MÁS DE UNA IP
pública, y el cupo se cuenta por IP. O sea que el total que pasa es 30 x la
cantidad de IPs de salida, no 30.
"""

import base64
import collections
import concurrent.futures
import os
import pickle
import sys
import time

import django
import requests

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE_DIR)
sys.path.insert(0, HERE)
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
django.setup()

from django.db import connection  # noqa: E402

from e2e import check, summary  # noqa: E402

URL = "https://friese-production.up.railway.app/api/public/shipment/00000000-0000-0000-0000-000000000000/"
TOTAL = int(sys.argv[1]) if len(sys.argv) > 1 else 100
CONCURRENCIA = int(sys.argv[2]) if len(sys.argv) > 2 else 8


def contadores():
    with connection.cursor() as cur:
        cur.execute("SELECT cache_key, value FROM friese_cache_table "
                    "WHERE cache_key LIKE %s", ["%throttle_public_burst%"])
        salida = {}
        for clave, valor in cur.fetchall():
            try:
                salida[clave.split("burst_")[-1]] = len(pickle.loads(base64.b64decode(valor)))
            except Exception:  # noqa: BLE001
                pass
        return salida


with connection.cursor() as cur:
    cur.execute("DELETE FROM friese_cache_table WHERE cache_key LIKE %s", ["%throttle_%"])
    print(f"  contadores borrados: {cur.rowcount}")

time.sleep(2)


def pegar(_):
    return requests.get(URL, timeout=30).status_code


arranque = time.time()
with concurrent.futures.ThreadPoolExecutor(max_workers=CONCURRENCIA) as pool:
    codigos = list(pool.map(pegar, range(TOTAL)))
tardo = time.time() - arranque

conteo = collections.Counter(codigos)
por_ip = contadores()
print(f"\n  {TOTAL} requests con concurrencia {CONCURRENCIA}, en {tardo:.1f}s: {dict(conteo)}")
print(f"  timestamps guardados por IP de salida: {por_ip}")

ips = len(por_ip)
pasaron = conteo.get(404, 0)
esperado = 30 * ips

check(ips >= 1, f"el backend ve {ips} IP(s) de salida de esta máquina", str(list(por_ip)))
check(all(n <= 35 for n in por_ip.values()),
      "NINGUNA IP supera el cupo de 30 por minuto (tolerancia por la carrera de DRF)",
      str(por_ip))
check(pasaron <= esperado * 1.25,
      f"el total que pasa es del orden de 30 x {ips} IP = {esperado}, no un múltiplo de los workers",
      f"pasaron {pasaron}")
check(conteo.get(429, 0) > 0, "el resto corta con 429")

r = requests.get(URL, timeout=30)
check(r.status_code == 429 and "Retry-After" in r.headers,
      "el 429 lo emite Django (trae Retry-After)", r.headers.get("Retry-After"))
check("detail" in r.text.lower() or "solicitud" in r.text.lower(),
      "el 429 es el de DRF, con su mensaje, no un corte del proxy", r.text[:90])

sys.exit(summary("rate limit en producción con cache compartido"))
