"""Tarea 12.2 — medición de rendimiento. Los números del informe salen de acá.

    python smoke_tests/perf_audit.py            # queries + peso de las respuestas
    python smoke_tests/perf_audit.py indices    # índices y volumen REAL (Supabase)
    python smoke_tests/perf_audit.py prod       # latencia contra api.friese.com.ar
    python smoke_tests/perf_audit.py todo

**No toca Supabase** en el modo por defecto: crea una base SQLite de test aparte y
la borra al terminar. El conteo de queries lo decide el ORM, no el motor, así que
los números valen igual contra PostgreSQL — lo que NO vale es el tiempo en ms, que
acá sale sin red y contra SQLite (por eso los tiempos se reportan solo como orden
de magnitud de la serialización, nunca como latencia de producción).

Los modos `indices` y `prod` sí salen a la red, pero **solo leen**: `pg_indexes` y
`count(*)` sobre la base, y GETs contra endpoints públicos del backend.

El changelist del admin se mide con `items_for_result()`, que es la función que el
template usa para dibujar cada celda: da el mismo número de queries que la pantalla
real sin tener que renderizar el template (el motor de templates de Django 5.1 no
corre en Python 3.14, que puede ser el intérprete de la máquina de desarrollo).
"""

import os
import re
import sys
import time
import uuid
from collections import Counter

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BASE_DIR)

MODO = (sys.argv[1] if len(sys.argv) > 1 else "queries").lower()
API_PROD = "https://api.friese.com.ar"

# Forma del remito con la que se mide. Es la del uso real: unos pocos productos y
# un par de fotos de despacho.
ITEMS_POR_REMITO = 3
FOTOS_POR_REMITO = 2


def titulo(texto):
    print()
    print("=" * 94)
    print(texto)
    print("=" * 94)


# --------------------------------------------------------------------------
# Modo `indices` — contra la base REAL, solo lectura.
# --------------------------------------------------------------------------
def medir_indices():
    # Se lee el .env con dotenv_values y NO con load_dotenv: en el modo `todo`,
    # medir_queries() ya dejó DATABASE_URL apuntando a la SQLite de test, y
    # load_dotenv() no pisa una variable que ya está en el entorno.
    from dotenv import dotenv_values

    import psycopg

    dsn = dotenv_values(os.path.join(BASE_DIR, ".env")).get("DATABASE_URL") or os.environ.get(
        "DATABASE_URL", ""
    )
    if not dsn.startswith("postgres"):
        print("\n  DATABASE_URL no apunta a PostgreSQL: se saltea el modo `indices`.")
        return

    tablas = [
        "shipments_shipment", "shipments_shipmentitem", "shipments_evidence",
        "catalog_product", "companies_company", "companies_usagelog",
        "users_user", "friese_cache_table",
    ]
    with psycopg.connect(dsn, connect_timeout=20) as conn:
        with conn.cursor() as cur:
            titulo("ÍNDICES REALES (pg_indexes)")
            cur.execute(
                "SELECT tablename, indexname, indexdef FROM pg_indexes "
                "WHERE schemaname='public' AND tablename = ANY(%s) "
                "ORDER BY tablename, indexname",
                (tablas,),
            )
            actual = None
            for tabla, nombre, definicion in cur.fetchall():
                if tabla != actual:
                    print(f"\n-- {tabla}")
                    actual = tabla
                columnas = definicion.split("USING")[-1].strip()
                unico = "UNIQUE " if "UNIQUE INDEX" in definicion else ""
                print(f"   {unico}{nombre} -> {columnas}")

            titulo("VOLUMEN ACTUAL")
            for tabla in tablas:
                cur.execute(f'SELECT count(*) FROM "{tabla}"')
                print(f"   {tabla:<34} {cur.fetchone()[0]:>8} filas")


# --------------------------------------------------------------------------
# Modo `prod` — latencia del backend desplegado, solo GETs.
# --------------------------------------------------------------------------
def medir_prod():
    import requests

    def sondear(etiqueta, url, veces=5):
        print(f"\n  {etiqueta}")
        for i in range(1, veces + 1):
            t0 = time.perf_counter()
            resp = requests.get(url(), timeout=30)
            ms = (time.perf_counter() - t0) * 1000
            print(f"    req{i}  {ms:>7.0f} ms  HTTP {resp.status_code}")

    titulo("LATENCIA DE PRODUCCIÓN (incluye la red desde esta máquina)")
    print("  Para separar el tiempo del servidor del de la red, comparar los dos")
    print("  sondeos: el primero NO pasa por el throttle, el segundo SÍ (y el")
    print("  throttle son 12 queries contra la tabla de cache en Supabase).")
    sondear("A) /admin/login/ — sin throttle", lambda: f"{API_PROD}/admin/login/")
    sondear(
        "B) /api/public/shipment/<uuid inexistente>/ — con throttle (404)",
        lambda: f"{API_PROD}/api/public/shipment/{uuid.uuid4()}/",
    )
    print("\n  Cold start: este sondeo mide el backend CALIENTE. Para el frío hay que")
    print("  dejarlo sin tráfico más de 10 minutos (`conn_max_age=600` en settings)")
    print("  y recién ahí correr el modo `prod`.")


# --------------------------------------------------------------------------
# Modo `queries` — conteo de queries y peso de las respuestas, en SQLite local.
# --------------------------------------------------------------------------
def medir_queries():
    os.environ["DATABASE_URL"] = "sqlite:///" + os.path.join(BASE_DIR, "perf_audit_tmp.sqlite3")
    os.environ["DJANGO_ENV"] = "development"
    os.environ["DJANGO_SETTINGS_MODULE"] = "config.settings"
    os.environ.setdefault("SECRET_KEY", "django-insecure-perf-audit")
    # setup_test_environment() de Django parchea ALLOWED_HOSTS, pero también instrumenta
    # el renderizado de templates (que no corre en Python 3.14): se agrega a mano.
    os.environ["ALLOWED_HOSTS"] = "localhost,127.0.0.1,testserver"

    import django

    django.setup()

    from django.db import connection
    from django.test.utils import CaptureQueriesContext

    connection.creation.create_test_db(verbosity=0)

    from unittest import mock

    from django.contrib import admin as dj_admin
    from django.contrib.admin.templatetags.admin_list import items_for_result
    from django.contrib.auth import get_user_model
    from django.core.files.uploadedfile import SimpleUploadedFile
    from django.test import RequestFactory
    from django.utils import timezone
    from rest_framework.test import APIClient
    from rest_framework_simplejwt.tokens import RefreshToken

    from catalog.models import Product
    from companies.models import Company
    from shipments.models import Evidence, Shipment, ShipmentItem

    User = get_user_model()

    def poblar(n_remitos, sufijo, fotos_con_item=False):
        """Crea una empresa con n remitos DESPACHADOS, sus ítems y sus fotos.

        El paso a `dispatched` va por UPDATE de queryset para no disparar el signal
        de despacho (que descuenta el trial y manda el email): para contar queries de
        lectura no hace falta, y así el escenario se arma en dos INSERT masivos.
        """
        company = Company.objects.create(name=f"Corralón {sufijo}", email="c@x.com")
        operador = User.objects.create_user(
            username=f"op{sufijo}", password="x", company=company, role=User.OPERATOR
        )
        productos = [
            Product.objects.create(company=company, name=f"Producto {i}", unit=Product.BOLSAS)
            for i in range(ITEMS_POR_REMITO)
        ]
        Shipment.objects.bulk_create([
            Shipment(company=company, operator=operador, receiver_name=f"Receptor {i}",
                     receiver_email="receptor@x.com", status=Shipment.DRAFT)
            for i in range(n_remitos)
        ])
        remitos = list(Shipment.objects.filter(company=company).order_by("id"))
        ShipmentItem.objects.bulk_create([
            ShipmentItem(shipment=r, product=productos[i], quantity=10)
            for r in remitos for i in range(ITEMS_POR_REMITO)
        ])
        primer_item = {}
        if fotos_con_item:
            for item in ShipmentItem.objects.filter(shipment__company=company).order_by("id"):
                primer_item.setdefault(item.shipment_id, item)
        Evidence.objects.bulk_create([
            Evidence(shipment=r, shipment_item=primer_item.get(r.pk), type=Evidence.DISPATCH,
                     uploaded_by=operador, file_url="https://r2.example/foto.jpg",
                     file_hash="a" * 64)
            for r in remitos for _ in range(FOTOS_POR_REMITO)
        ])
        for r in remitos:
            Shipment.objects.filter(pk=r.pk).update(
                status=Shipment.DISPATCHED, dispatched_at=timezone.now(),
                public_token=uuid.uuid4())
        return company, operador, list(Shipment.objects.filter(company=company).order_by("id"))

    def cliente_jwt(usuario):
        """APIClient autenticado como lo hace producción: Bearer + JWT.

        `force_authenticate()` NO sirve para contar queries: reutiliza el objeto User
        que uno ya tiene en memoria (con `.company` cacheada) y además se saltea la
        query con la que la autenticación carga al usuario. Contra un JWT real, cada
        request vuelve a cargar el usuario y su empresa, que es lo que pasa de verdad.
        """
        cliente = APIClient()
        cliente.credentials(HTTP_AUTHORIZATION=f"Bearer {RefreshToken.for_user(usuario).access_token}")
        return cliente

    def medir(etiqueta, fn):
        with CaptureQueriesContext(connection) as ctx:
            resp = fn()
        n = len(ctx.captured_queries)
        print(f"  {etiqueta:<58} {n:>4} queries   HTTP {getattr(resp, 'status_code', '-')}")
        return n, ctx.captured_queries

    def desglosar(queries, indent="      "):
        """Agrupa las queries por (verbo, tabla), para que un N+1 salte a la vista."""
        c = Counter()
        for q in queries:
            sql = q["sql"]
            verbo = sql.split()[0].upper()
            # La tabla se saca del SQL COMPLETO: recortar antes se come el FROM,
            # porque la lista de columnas de un SELECT de Django es larguísima.
            for palabra in ("FROM", "INTO", "UPDATE"):
                if palabra in sql:
                    tabla = sql.split(palabra, 1)[1].strip().split()[0].strip('"')
                    break
            else:
                tabla = "—"
            c[(verbo, tabla)] += 1
        for (verbo, tabla), veces in c.most_common(6):
            marca = "   <-- N+1" if veces > 3 else ""
            print(f"{indent}x{veces:<4} {verbo:<6} {tabla}{marca}")

    # --- API del operador y del receptor -----------------------------------
    titulo("QUERIES POR ENDPOINT DE LA API  "
           f"(cada remito: {ITEMS_POR_REMITO} ítems, {FOTOS_POR_REMITO} fotos)")
    print("  Autenticado con JWT real, igual que producción: de cada conteo, 1 query es")
    print("  la carga del usuario y otra la de su empresa (ver `cliente_jwt`).")
    resultados = {}
    for n_remitos in (20, 100):
        _, operador, remitos = poblar(n_remitos, str(n_remitos))
        api = cliente_jwt(operador)
        print(f"\n  --- empresa con {n_remitos} remitos ---")
        r0 = remitos[0]
        resultados[f"lista_{n_remitos}"], q_lista = medir(
            "GET  /api/shipments/  (lista)", lambda: api.get("/api/shipments/"))
        resultados[f"detalle_{n_remitos}"], _ = medir(
            "GET  /api/shipments/{id}/  (detalle)", lambda: api.get(f"/api/shipments/{r0.pk}/"))
        resultados[f"productos_{n_remitos}"], _ = medir(
            "GET  /api/products/", lambda: api.get("/api/products/"))
        publico = APIClient()
        resultados[f"publico_{n_remitos}"], q_pub = medir(
            "GET  /api/public/shipment/{token}/  (1ra visita)",
            lambda: publico.get(f"/api/public/shipment/{r0.public_token}/"))
        resultados[f"publico2_{n_remitos}"], _ = medir(
            "GET  /api/public/shipment/{token}/  (2da visita)",
            lambda: publico.get(f"/api/public/shipment/{r0.public_token}/"))
        if n_remitos == 20:
            print("\n    Desglose de la lista:")
            desglosar(q_lista)
            print("\n    Desglose del endpoint público (ojo la tabla de cache):")
            desglosar(q_pub)

    titulo("¿ESCALA CON EL VOLUMEN? (20 vs 100 remitos)")
    for clave, nombre in (("lista", "GET /api/shipments/"),
                          ("detalle", "GET /api/shipments/{id}/"),
                          ("productos", "GET /api/products/"),
                          ("publico", "GET /api/public/shipment/{token}/")):
        a, b = resultados[f"{clave}_20"], resultados[f"{clave}_100"]
        veredicto = "CONSTANTE — sin N+1" if a == b else f"CRECE (+{b - a}) — hay N+1"
        print(f"  {nombre:<42} 20: {a:>3}   100: {b:>3}   {veredicto}")

    # --- Django Admin -------------------------------------------------------
    titulo("QUERIES DEL DJANGO ADMIN (changelist, 100 filas por página)")
    _, _, remitos_admin = poblar(60, "admin", fotos_con_item=True)
    root = User.objects.create_superuser(username="root", password="x", email="root@x.com")
    rf = RequestFactory()

    def changelist(modelo, etiqueta):
        ma = dj_admin.site._registry[modelo]
        req = rf.get("/admin/")
        req.user = root
        with CaptureQueriesContext(connection) as ctx:
            cl = ma.get_changelist_instance(req)
            cl.formset = None
            filas = list(cl.result_list)
            for obj in filas:
                list(items_for_result(cl, obj, None))
        print(f"  {etiqueta:<58} {len(ctx.captured_queries):>4} queries  ({len(filas)} filas)")
        desglosar(ctx.captured_queries)
        print()

    changelist(Evidence, "/admin/shipments/evidence/")
    changelist(Shipment, "/admin/shipments/shipment/")
    changelist(ShipmentItem, "/admin/shipments/shipmentitem/")

    # --- Escrituras ---------------------------------------------------------
    titulo("QUERIES DE LAS ESCRITURAS")
    company = remitos_admin[0].company
    operador = remitos_admin[0].operator
    api = cliente_jwt(operador)
    producto = Product.objects.filter(company=company).first()
    borrador = Shipment.objects.create(company=company, operator=operador,
                                       receiver_name="Borrador", receiver_email="r@x.com")
    ShipmentItem.objects.create(shipment=borrador, product=producto, quantity=5)

    foto = SimpleUploadedFile("f.jpg", b"\xff\xd8\xff" + b"0" * 40000, content_type="image/jpeg")
    with mock.patch("shipments.views.upload_evidence_file",
                    return_value=("https://r2.example/x.jpg", "b" * 64)):
        n, queries = medir("POST /api/shipments/{id}/evidence/  (subir 1 foto)",
                           lambda: api.post(f"/api/shipments/{borrador.pk}/evidence/",
                                            {"file": foto}, format="multipart"))
    for i, q in enumerate(queries, 1):
        print(f"      {i:>2}. {q['sql'][:100]}")

    with mock.patch("shipments.signals.send_dispatch_email", return_value=None):
        n, queries = medir("PATCH /api/shipments/{id}/dispatch/",
                           lambda: api.patch(f"/api/shipments/{borrador.pk}/dispatch/"))
    for i, q in enumerate(queries, 1):
        print(f"      {i:>2}. {q['sql'][:100]}")

    # --- Peso de la respuesta sin paginación --------------------------------
    titulo("PESO DE GET /api/shipments/ SIN PAGINACIÓN")
    print("  (el tiempo es SQLite local sin red: sirve para ver cómo crece, no como")
    print("   latencia de producción)")
    print(f"\n  {'remitos':>9} {'JSON':>12} {'KB/remito':>11} {'serialización':>15}")
    for n in (10, 50, 200, 1000, 3000):
        _, op_n, _ = poblar(n, f"peso{n}")
        cliente = cliente_jwt(op_n)
        cliente.get("/api/shipments/")  # calentar
        tiempos = []
        for _ in range(3):
            t0 = time.perf_counter()
            resp = cliente.get("/api/shipments/")
            tiempos.append((time.perf_counter() - t0) * 1000)
        peso = len(resp.content)
        print(f"  {n:>9} {peso / 1024:>9.1f} KB {peso / n / 1024:>10.2f} {min(tiempos):>12.0f} ms")

    connection.creation.destroy_test_db(":memory:", verbosity=0)
    sqlite_tmp = os.path.join(BASE_DIR, "perf_audit_tmp.sqlite3")
    if os.path.exists(sqlite_tmp):
        os.remove(sqlite_tmp)


if MODO in ("queries", "todo"):
    medir_queries()
if MODO in ("indices", "todo"):
    medir_indices()
if MODO in ("prod", "todo"):
    medir_prod()
if MODO not in ("queries", "indices", "prod", "todo"):
    print(__doc__)
    sys.exit(1)
