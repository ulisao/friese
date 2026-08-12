"""Fase 6.6 — cuánto tarda UNA operación del cache contra Supabase desde acá.

Sirve para saber si los números de `cache_race.py` dicen algo del producto o
solo de la distancia entre esta máquina y la base.
"""

import os
import statistics
import sys
import time

import django

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BASE_DIR)
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
django.setup()

from django.core.cache import cache  # noqa: E402
from django.db import connection  # noqa: E402

cache.set("smoke66-ping", [1, 2, 3], 60)  # calienta la conexión

tiempos = []
for i in range(10):
    t = time.perf_counter()
    cache.get("smoke66-ping")
    cache.set("smoke66-ping", list(range(i)), 60)
    tiempos.append((time.perf_counter() - t) * 1000)

print(f"get+set contra la tabla de cache: mediana {statistics.median(tiempos):.0f} ms "
      f"(min {min(tiempos):.0f} / max {max(tiempos):.0f})")

t = time.perf_counter()
with connection.cursor() as cur:
    cur.execute("SELECT 1")
    cur.fetchone()
print(f"SELECT 1 pelado contra Supabase: {(time.perf_counter() - t) * 1000:.0f} ms")

# El throttle hace get+set por CADA una de las dos ventanas (burst y sustained).
print(f"\ncosto agregado por request pública: ~{statistics.median(tiempos) * 2:.0f} ms "
      f"(dos ventanas x get+set)")
cache.delete("smoke66-ping")
