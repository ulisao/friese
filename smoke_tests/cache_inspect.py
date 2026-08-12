"""Fase 6.6 — qué hay REALMENTE en la tabla de cache que usa el rate limiting."""

import base64
import os
import pickle
import sys
from datetime import datetime, timezone

import django

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BASE_DIR)
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
django.setup()

from django.db import connection  # noqa: E402

with connection.cursor() as cur:
    cur.execute("SELECT cache_key, value, expires FROM friese_cache_table ORDER BY expires DESC")
    filas = cur.fetchall()

print(f"filas en friese_cache_table: {len(filas)}\n")
ahora = datetime.now(timezone.utc)
for clave, valor, expira in filas:
    try:
        contenido = pickle.loads(base64.b64decode(valor.encode()))
    except Exception as exc:  # noqa: BLE001
        contenido = f"<no se pudo decodificar: {exc}>"
    if isinstance(contenido, list):
        resumen = f"{len(contenido)} timestamps"
        if contenido:
            resumen += (f" | más viejo hace {ahora.timestamp() - min(contenido):.0f}s"
                        f" | más nuevo hace {ahora.timestamp() - max(contenido):.0f}s")
    else:
        resumen = repr(contenido)[:80]
    print(f"{clave}")
    print(f"   {resumen}")
    print(f"   vence en {(expira - ahora).total_seconds():.0f}s\n")
