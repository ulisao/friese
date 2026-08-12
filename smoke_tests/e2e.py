"""Fase 6.6 — Smoke test end-to-end contra PRODUCCIÓN.

Recorre el flujo completo del MVP contra las URLs reales de producción:

    alta de empresa -> alta de operador (token del QR) -> creación de remito ->
    despacho con foto -> email al receptor -> aceptación / disputa -> cierre

Uso (cada fase deja su estado en smoke_tests/state.json):

    python smoke_tests/e2e.py setup      # superusuario temporal (se borra al final)
    python smoke_tests/e2e.py admin      # empresa + primer admin + productos + invitación
    python smoke_tests/e2e.py operator   # alta del operador, remitos, fotos y despacho
    python smoke_tests/e2e.py receiver   # el receptor abre el link, acepta y disputa
    python smoke_tests/e2e.py expire     # vence la ventana del remito C (para el cron)
    python smoke_tests/e2e.py cron       # verifica que el cron de Railway lo cerró
    python smoke_tests/e2e.py emails     # revisa en Resend los emails del flujo
    python smoke_tests/e2e.py cleanup    # borra TODO lo creado por el smoke test

La base y el bucket son los de producción: todo lo que crea lo borra en `cleanup`.
"""

import json
import os
import secrets
import sys
import urllib.request
from datetime import timedelta

import django
import requests

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BASE_DIR)
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
django.setup()

from django.conf import settings  # noqa: E402
from django.contrib.auth.hashers import make_password  # noqa: E402
from django.utils import timezone  # noqa: E402

from catalog.models import Product  # noqa: E402
from companies.models import Company, UsageLog  # noqa: E402
from shipments.models import Evidence, Shipment, ShipmentItem  # noqa: E402
from users.models import OperatorInvite, User  # noqa: E402

# --- Producción -------------------------------------------------------------
BACKEND = "https://api.friese.com.ar"
FRONTEND = "https://app.friese.com.ar"
API = f"{BACKEND}/api"

# Marca única de esta corrida: todo lo creado la lleva, así el cleanup es exacto.
TAG = "SMOKE66"
PHOTO = os.path.join(BASE_DIR, "frontend", "public",
                     "WhatsApp Image 2026-08-11 at 12.13.12.jpeg")
STATE_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "state.json")

# Casillas reales (plus-addressing de Gmail): los emails llegan de verdad y se
# pueden verificar en Resend, sin usar direcciones de terceros.
RECEIVER_EMAIL = "ulisessbaretta+smoke66@gmail.com"
COMPANY_ADMIN_EMAIL = "ulisessbaretta+smoke66admin@gmail.com"

OK, FAIL = [], []


def check(cond, label, detail=""):
    (OK if cond else FAIL).append(label)
    print(("  OK   " if cond else "  FALLA ") + label + (f"  [{detail}]" if detail else ""))
    return cond


def summary(phase):
    print(f"\n=== {phase}: {len(OK)} OK, {len(FAIL)} fallas ===")
    for f in FAIL:
        print("  FALLA:", f)
    return 1 if FAIL else 0


def load():
    if os.path.exists(STATE_PATH):
        with open(STATE_PATH, encoding="utf-8") as fh:
            return json.load(fh)
    return {}


def save(state):
    with open(STATE_PATH, "w", encoding="utf-8") as fh:
        json.dump(state, fh, indent=2, ensure_ascii=False, default=str)


# --- Django Admin de producción por HTTPS -----------------------------------
def admin_login(username, password):
    """Inicia sesión en el Django Admin de producción y devuelve la sesión."""
    s = requests.Session()
    s.headers["User-Agent"] = "friese-smoke66/1.0"
    r = s.get(f"{BACKEND}/admin/login/", timeout=30)
    r.raise_for_status()
    r = s.post(
        f"{BACKEND}/admin/login/",
        data={
            "username": username,
            "password": password,
            "csrfmiddlewaretoken": s.cookies["csrftoken"],
            "next": "/admin/",
        },
        headers={"Referer": f"{BACKEND}/admin/login/"},
        allow_redirects=False,
        timeout=30,
    )
    return s, r


def admin_post(session, path, data):
    """POST a un formulario del admin, tomando el CSRF de la propia pantalla."""
    url = f"{BACKEND}{path}"
    r = session.get(url, timeout=30)
    r.raise_for_status()
    payload = dict(data)
    payload["csrfmiddlewaretoken"] = session.cookies["csrftoken"]
    payload.setdefault("_save", "Grabar")
    r = session.post(url, data=payload, headers={"Referer": url},
                     allow_redirects=False, timeout=60)
    if r.status_code == 200 and "errorlist" in r.text:
        # El admin re-renderiza el formulario con los errores: los extraigo para
        # que la falla se lea, en vez de un 200 mudo.
        import re
        errs = re.findall(r'<ul class="errorlist[^"]*"[^>]*>(.*?)</ul>', r.text, re.S)
        print("    errores del formulario:", " | ".join(
            re.sub(r"<[^>]+>", " ", e).strip() for e in errs)[:500])
    return r


# --- Fases ------------------------------------------------------------------
def phase_setup():
    """Superusuario temporal para operar el admin de producción."""
    state = load()
    username = f"smoke66_root_{secrets.token_hex(3)}"
    password = secrets.token_urlsafe(18)
    user = User.objects.create(
        username=username,
        email="",
        password=make_password(password),
        is_staff=True,
        is_superuser=True,
        is_active=True,
    )
    print(f"  superusuario temporal creado: {username} (id {user.id})")
    check(user.is_superuser and user.is_staff, "el superusuario temporal queda staff + superuser")

    s, r = admin_login(username, password)
    check(r.status_code == 302, "login al Django Admin de PRODUCCIÓN por HTTPS", f"HTTP {r.status_code}")
    home = s.get(f"{BACKEND}/admin/", timeout=30)
    check(home.status_code == 200 and "Companies" in home.text or "Empresas" in home.text,
          "el admin de producción responde con el índice", f"HTTP {home.status_code}")

    state.update({"root_username": username, "root_password": password, "root_id": user.id})
    save(state)
    return summary("setup")


def phase_admin():
    """Alta de empresa + primer admin, productos y la invitación del QR."""
    state = load()
    s, r = admin_login(state["root_username"], state["root_password"])
    check(r.status_code == 302, "login como superadmin")

    # 1) Alta de empresa + su primer admin, en UN formulario (tarea 4.4).
    company_name = f"Transportes {TAG} SRL"
    admin_username = f"{TAG.lower()}_admin"
    admin_password = secrets.token_urlsafe(18)
    r = admin_post(s, "/admin/companies/company/add/", {
        "name": company_name,
        "email": COMPANY_ADMIN_EMAIL,
        "phone": "+54 9 341 555-0166",
        "plan": "",
        "is_active": "on",
        "trial_shipments_remaining": "10",
        "admin_username": admin_username,
        "admin_email": COMPANY_ADMIN_EMAIL,
        "admin_password": admin_password,
        "admin_password_confirm": admin_password,
    })
    check(r.status_code == 302, "alta de empresa + primer admin desde el admin de producción",
          f"HTTP {r.status_code}")

    company = Company.objects.filter(name=company_name).first()
    check(company is not None, "la empresa quedó creada en la base de producción")
    if company is None:
        return summary("admin")
    check(company.trial_shipments_remaining == 10, "la empresa arranca con 10 remitos de trial",
          f"trial={company.trial_shipments_remaining}")
    check(company.is_active, "la empresa queda activa")

    company_admin = User.objects.filter(username=admin_username).first()
    check(company_admin is not None, "el primer admin de la empresa quedó creado")
    check(company_admin and company_admin.company_id == company.id,
          "el admin quedó atado a su empresa")
    check(company_admin and company_admin.role == User.ADMIN and company_admin.is_staff,
          "el admin es role=admin y tiene acceso al panel")
    check(company_admin and company_admin.groups.filter(name="Admin de empresa").exists(),
          "el admin quedó en el grupo «Admin de empresa»")

    # 2) El ADMIN DE LA EMPRESA entra al panel con su usuario y carga su catálogo.
    sa, ra = admin_login(admin_username, admin_password)
    check(ra.status_code == 302, "el admin de la empresa entra al panel de producción",
          f"HTTP {ra.status_code}")

    productos = [("Cemento Portland x50", "bolsas"), ("Arena fina a granel", "ton")]
    product_ids = []
    for name, unit in productos:
        rp = admin_post(sa, "/admin/catalog/product/add/", {
            "company": str(company.id),
            "name": f"{name} {TAG}",
            "description": "Producto de prueba del smoke test 6.6.",
            "barcode": "",
            "is_active": "on",
            "unit": unit,
        })
        p = Product.objects.filter(company=company, name=f"{name} {TAG}").first()
        check(rp.status_code == 302 and p is not None, f"el admin carga el producto «{name}»",
              f"HTTP {rp.status_code}")
        if p:
            product_ids.append(p.id)

    # Aislamiento: el admin de la empresa nueva no ve datos de otra empresa.
    otra = Company.objects.exclude(pk=company.pk).first()
    if otra:
        # allow_redirects=False: el admin contesta 302 al índice cuando el objeto
        # no está en el queryset del tenant. Siguiendo el redirect se vería un 200
        # del índice y parecería un acceso concedido.
        rr = sa.get(f"{BACKEND}/admin/companies/company/{otra.pk}/change/",
                    allow_redirects=False, timeout=30)
        check(rr.status_code in (302, 403, 404),
              "el admin de la empresa NO puede abrir la ficha de otra empresa",
              f"HTTP {rr.status_code} -> {rr.headers.get('Location')}")
        rs = sa.get(f"{BACKEND}/admin/shipments/shipment/", timeout=30)
        check(rs.status_code == 200 and "Corralón Demo" not in rs.text,
              "el listado de remitos del admin no muestra remitos de otra empresa")

    # 3) Invitación de operador: el token que va en el QR (tarea 1.5).
    expires = timezone.localtime(timezone.now() + timedelta(days=7))
    ri = admin_post(sa, "/admin/users/operatorinvite/add/", {
        "company": str(company.id),
        "expires_at_0": expires.strftime("%d/%m/%Y"),
        "expires_at_1": expires.strftime("%H:%M:%S"),
    })
    invite = OperatorInvite.objects.filter(company=company).order_by("-id").first()
    check(ri.status_code == 302 and invite is not None,
          "el admin genera la invitación de operador (token del QR)", f"HTTP {ri.status_code}")
    if invite:
        check(invite.token is not None and not invite.is_used,
              "la invitación trae token UUID y arranca sin usar", str(invite.token))

    state.update({
        "company_id": company.id,
        "company_name": company_name,
        "admin_username": admin_username,
        "admin_password": admin_password,
        "product_ids": product_ids,
        "invite_token": str(invite.token) if invite else None,
        "invite_id": invite.id if invite else None,
    })
    save(state)
    return summary("admin")


def phase_operator():
    """Alta del operador por el token del QR, remitos, fotos y despacho."""
    state = load()

    # 1) Alta del operador con el token de la invitación (lo que hay detrás del QR).
    op_username = f"{TAG.lower()}_operador"
    op_password = secrets.token_urlsafe(18)
    r = requests.post(f"{API}/auth/register-operator/", json={
        "token": state["invite_token"], "username": op_username, "password": op_password,
    }, timeout=30)
    check(r.status_code == 201, "alta del operador con el token del QR contra producción",
          f"HTTP {r.status_code} {r.text[:120]}")

    operator = User.objects.filter(username=op_username).first()
    check(operator is not None and operator.role == User.OPERATOR,
          "el operador quedó creado con role=operator")
    check(operator is not None and operator.company_id == state["company_id"],
          "el operador quedó en la empresa de la invitación")
    invite = OperatorInvite.objects.filter(pk=state["invite_id"]).first()
    check(invite is not None and invite.is_used, "la invitación quedó marcada como usada")

    r = requests.post(f"{API}/auth/register-operator/", json={
        "token": state["invite_token"], "username": f"{op_username}_bis", "password": op_password,
    }, timeout=30)
    check(r.status_code == 400, "reusar el token del QR es rechazado", f"HTTP {r.status_code}")

    # 2) Login del operador (individual, usuario + contraseña).
    r = requests.post(f"{API}/auth/login/", json={"username": op_username, "password": op_password},
                      timeout=30)
    check(r.status_code == 200 and "access" in r.json(), "login del operador contra producción",
          f"HTTP {r.status_code}")
    tokens = r.json()
    auth = {"Authorization": f"Bearer {tokens['access']}"}

    r = requests.post(f"{API}/auth/refresh/", json={"refresh": tokens["refresh"]}, timeout=30)
    check(r.status_code == 200 and "access" in r.json(), "el refresh del JWT rota el token",
          f"HTTP {r.status_code}")
    r = requests.post(f"{API}/auth/refresh/", json={"refresh": tokens["refresh"]}, timeout=30)
    check(r.status_code == 401, "el refresh viejo queda invalidado (blacklist)",
          f"HTTP {r.status_code}")

    # 3) El operador ve su catálogo.
    r = requests.get(f"{API}/products/", headers=auth, timeout=30)
    products = r.json() if r.status_code == 200 else []
    check(r.status_code == 200 and len(products) == len(state["product_ids"]),
          "el operador ve los productos de su empresa", f"HTTP {r.status_code}, {len(products)} productos")

    # 4) Tres remitos: A acepta, B disputa, C se cierra solo por el cron.
    with open(PHOTO, "rb") as fh:
        photo_bytes = fh.read()

    shipments = {}
    for key, receiver in (("A", "Acopio San Lorenzo"), ("B", "Corralón del Norte"),
                          ("C", "Depósito Ruta 9")):
        r = requests.post(f"{API}/shipments/", headers=auth, json={
            "receiver_name": f"{receiver} ({TAG})",
            "receiver_email": RECEIVER_EMAIL,
            "receiver_phone": "+54 9 341 555-0177",
        }, timeout=30)
        check(r.status_code == 201, f"remito {key}: creado", f"HTTP {r.status_code}")
        sid = r.json()["id"]
        check(r.json()["status"] == "draft" and r.json().get("public_token") is None,
              f"remito {key}: nace en draft y sin public_token")

        for pid, qty in zip(state["product_ids"], ("50.00", "3.50")):
            ri = requests.post(f"{API}/shipments/{sid}/items/", headers=auth,
                               json={"product": pid, "quantity": qty, "notes": ""}, timeout=30)
            check(ri.status_code == 201, f"remito {key}: ítem agregado", f"HTTP {ri.status_code}")

        # La foto de despacho: en A se saca en draft (como hace el frontend en 2.8)
        # y en B/C después de despachar. Los dos estados son válidos (tarea 2.4).
        if key == "A":
            re_ = requests.post(f"{API}/shipments/{sid}/evidence/", headers=auth,
                                files={"file": ("carga.jpg", photo_bytes, "image/jpeg")},
                                timeout=120)
            check(re_.status_code == 201, f"remito {key}: foto de despacho subida en draft",
                  f"HTTP {re_.status_code} {re_.text[:120]}")

        rd = requests.patch(f"{API}/shipments/{sid}/dispatch/", headers=auth, timeout=60)
        check(rd.status_code == 200, f"remito {key}: despachado", f"HTTP {rd.status_code}")
        token = rd.json().get("public_token")
        check(bool(token), f"remito {key}: el despacho generó public_token", str(token))

        if key != "A":
            re_ = requests.post(f"{API}/shipments/{sid}/evidence/", headers=auth,
                                files={"file": ("carga.jpg", photo_bytes, "image/jpeg")},
                                timeout=120)
            check(re_.status_code == 201, f"remito {key}: foto de despacho subida en dispatched",
                  f"HTTP {re_.status_code} {re_.text[:120]}")

        ri = requests.post(f"{API}/shipments/{sid}/items/", headers=auth,
                           json={"product": state["product_ids"][0], "quantity": "1.00"}, timeout=30)
        check(ri.status_code == 400, f"remito {key}: despachado queda inmutable (no admite ítems)",
              f"HTTP {ri.status_code}")

        shipments[key] = {"id": sid, "token": token}

    # 5) La foto es accesible por su URL pública de R2 (es la evidencia del cliente).
    ev = Evidence.objects.filter(shipment_id=shipments["A"]["id"]).first()
    if ev:
        rf = requests.get(ev.file_url, timeout=60)
        check(rf.status_code == 200 and rf.headers.get("content-type", "").startswith("image/"),
              "la foto de despacho se abre desde R2 sin auth",
              f"HTTP {rf.status_code} {rf.headers.get('content-type')}")
        check(len(rf.content) == len(photo_bytes), "la foto en R2 es byte a byte la que se subió")

    # 6) Trial y UsageLog (sección 6).
    company = Company.objects.get(pk=state["company_id"])
    check(company.trial_shipments_remaining == 7,
          "el trial bajó de 10 a 7 con los 3 despachos", f"trial={company.trial_shipments_remaining}")
    usage = UsageLog.objects.filter(company=company).first()
    check(usage is not None and usage.shipments_created == 3,
          "UsageLog cuenta los 3 remitos del mes",
          f"shipments={getattr(usage, 'shipments_created', None)}")
    check(usage is not None and usage.photos_uploaded == 3,
          "UsageLog cuenta las 3 fotos", f"photos={getattr(usage, 'photos_uploaded', None)}")

    state.update({"operator_username": op_username, "operator_password": op_password,
                  "shipments": shipments})
    save(state)
    return summary("operator")


def phase_receiver():
    """El receptor abre el link único, acepta uno y disputa otro."""
    state = load()
    A, B, C = state["shipments"]["A"], state["shipments"]["B"], state["shipments"]["C"]

    with open(PHOTO, "rb") as fh:
        photo_bytes = fh.read()

    # 1) Primera apertura del link: sella link_opened_at y la ventana de 48hs.
    for key, sh in (("A", A), ("B", B), ("C", C)):
        r = requests.get(f"{API}/public/shipment/{sh['token']}/", timeout=30)
        check(r.status_code == 200, f"remito {key}: el link público abre sin login",
              f"HTTP {r.status_code}")
        data = r.json()
        check(data["status"] == "dispatched", f"remito {key}: el receptor lo ve como despachado")
        check(len(data["items"]) == 2 and len(data["evidence"]) == 1,
              f"remito {key}: el receptor ve los 2 ítems y la foto de despacho")
        check(bool(data["link_opened_at"]) and bool(data["response_deadline"]),
              f"remito {key}: la primera apertura selló la ventana de respuesta")
        sh["link_opened_at"] = data["link_opened_at"]

    obj = Shipment.objects.get(pk=A["id"])
    first_open = obj.link_opened_at
    requests.get(f"{API}/public/shipment/{A['token']}/", timeout=30)
    obj.refresh_from_db()
    check(obj.link_opened_at == first_open,
          "remito A: reabrir el link NO pisa link_opened_at")
    check(obj.response_deadline == first_open + timedelta(hours=48),
          "remito A: la ventana de respuesta es de 48hs exactas")

    # 2) Remito A: conformidad.
    r = requests.post(f"{API}/public/shipment/{A['token']}/accept/", timeout=60)
    check(r.status_code == 200 and r.json()["status"] == "accepted",
          "remito A: el receptor da conformidad", f"HTTP {r.status_code}")
    check(Shipment.objects.get(pk=A["id"]).status == Shipment.ACCEPTED,
          "remito A: queda accepted en la base")
    r = requests.post(f"{API}/public/shipment/{A['token']}/accept/", timeout=30)
    check(r.status_code == 400, "remito A: no se puede responder dos veces", f"HTTP {r.status_code}")

    # 3) Remito B: queja con fotos de la carga recibida.
    r = requests.post(f"{API}/public/shipment/{B['token']}/dispute/",
                      json={"dispute_reason": "Faltan 5 bolsas"}, timeout=30)
    check(r.status_code == 400, "remito B: la queja sin foto se rechaza", f"HTTP {r.status_code}")

    for n in (1, 2):
        r = requests.post(f"{API}/public/shipment/{B['token']}/evidence/",
                          files={"file": (f"recepcion{n}.jpg", photo_bytes, "image/jpeg")},
                          timeout=120)
        check(r.status_code == 201, f"remito B: foto de recepción {n} subida",
              f"HTTP {r.status_code} {r.text[:120]}")

    reason = "Llegaron 45 bolsas de 50 y 2 rotas. Foto de la carga al descargar."
    r = requests.post(f"{API}/public/shipment/{B['token']}/dispute/",
                      json={"dispute_reason": reason}, timeout=60)
    check(r.status_code == 200 and r.json()["status"] == "disputed",
          "remito B: el receptor registra la queja", f"HTTP {r.status_code}")
    b = Shipment.objects.get(pk=B["id"])
    check(b.status == Shipment.DISPUTED and b.dispute_reason == reason,
          "remito B: queda disputed con el motivo guardado")
    check(b.evidence.filter(type=Evidence.RECEPTION).count() == 2,
          "remito B: quedaron las 2 fotos de recepción")

    # 4) El remito C queda intacto, esperando el cierre automático.
    check(Shipment.objects.get(pk=C["id"]).status == Shipment.DISPATCHED,
          "remito C: sigue dispatched, a la espera del cierre automático")

    save(state)
    return summary("receiver")


def phase_expire():
    """Vence la ventana del remito C para que la levante el cron de producción."""
    state = load()
    C = state["shipments"]["C"]
    updated = Shipment.objects.filter(pk=C["id"], status=Shipment.DISPATCHED).update(
        response_deadline=timezone.now() - timedelta(minutes=5)
    )
    check(updated == 1, "remito C: la ventana de respuesta quedó vencida hace 5 minutos")
    sh = Shipment.objects.get(pk=C["id"])
    print(f"  response_deadline: {sh.response_deadline}  |  ahora: {timezone.now()}")
    print("  El cron de Railway (*/15) tiene que cerrarlo solo en la próxima corrida.")
    state["expired_at"] = timezone.now().isoformat()
    save(state)
    return summary("expire")


def phase_cron():
    """Verifica que el cron de producción cerró el remito C, sin intervención."""
    state = load()
    C = state["shipments"]["C"]
    sh = Shipment.objects.get(pk=C["id"])
    print(f"  estado actual del remito C: {sh.status} | auto_closed={sh.auto_closed}")
    print(f"  venció a las {sh.response_deadline}; ahora son las {timezone.now()}")
    ok = check(sh.status == Shipment.ACCEPTED,
               "remito C: el cron de Railway lo cerró como accepted", sh.status)
    if ok:
        check(sh.auto_closed, "remito C: queda marcado auto_closed (conformidad por silencio)")
        r = requests.get(f"{API}/public/shipment/{C['token']}/", timeout=30)
        check(r.status_code == 200 and r.json()["status"] == "accepted" and r.json()["auto_closed"],
              "remito C: el receptor ve el cierre en su link")
    return summary("cron")


def phase_reminder_setup():
    """Deja un remito en condiciones de recordatorio (tarea 5.2) para el cron horario.

    Candidato = despachado hace más de REMINDER_AFTER_HOURS, con el link SIN abrir
    y sin recordatorio previo.
    """
    state = load()
    r = requests.post(f"{API}/auth/login/", json={
        "username": state["operator_username"], "password": state["operator_password"]}, timeout=30)
    auth = {"Authorization": f"Bearer {r.json()['access']}"}

    r = requests.post(f"{API}/shipments/", headers=auth, json={
        "receiver_name": f"Molino Sin Abrir ({TAG})",
        "receiver_email": RECEIVER_EMAIL,
        "receiver_phone": "",
    }, timeout=30)
    check(r.status_code == 201, "remito D (recordatorio): creado", f"HTTP {r.status_code}")
    sid = r.json()["id"]
    requests.post(f"{API}/shipments/{sid}/items/", headers=auth,
                  json={"product": state["product_ids"][0], "quantity": "10.00"}, timeout=30)
    rd = requests.patch(f"{API}/shipments/{sid}/dispatch/", headers=auth, timeout=60)
    check(rd.status_code == 200, "remito D: despachado", f"HTTP {rd.status_code}")

    horas = getattr(settings, "REMINDER_AFTER_HOURS", 24)
    Shipment.objects.filter(pk=sid).update(
        dispatched_at=timezone.now() - timedelta(hours=horas + 1))
    sh = Shipment.objects.get(pk=sid)
    check(sh.link_opened_at is None and sh.reminder_sent_at is None,
          "remito D: link sin abrir y sin recordatorio previo")
    print(f"  despachado (simulado) el {sh.dispatched_at}; el cron horario tiene que "
          f"mandarle el recordatorio en la próxima corrida en punto.")
    state["reminder_shipment_id"] = sid
    state["reminder_token"] = rd.json().get("public_token")
    save(state)
    return summary("reminder_setup")


def phase_reminder_check():
    """Verifica que el cron horario de Railway mandó el recordatorio."""
    state = load()
    sh = Shipment.objects.get(pk=state["reminder_shipment_id"])
    print(f"  remito D #{sh.pk}: reminder_sent_at = {sh.reminder_sent_at} (ahora {timezone.now()})")
    ok = check(sh.reminder_sent_at is not None,
               "remito D: el cron horario de Railway mandó el recordatorio")
    if ok:
        check(sh.link_opened_at is None,
              "remito D: el recordatorio no tocó el estado del remito")
        check(sh.status == Shipment.DISPATCHED, "remito D: sigue dispatched")
    return summary("reminder_check")


def phase_emails():
    """Revisa en Resend los emails que disparó el flujo."""
    state = load()
    req = urllib.request.Request(
        "https://api.resend.com/emails",
        headers={"Authorization": f"Bearer {settings.RESEND_API_KEY}",
                 "User-Agent": "friese-smoke66/1.0", "Accept": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        data = json.loads(resp.read().decode())

    mine = [e for e in data.get("data", []) if TAG in (e.get("subject") or "")
            or RECEIVER_EMAIL in (e.get("to") or [])
            or COMPANY_ADMIN_EMAIL in (e.get("to") or [])]
    print(f"  emails del smoke test en Resend: {len(mine)}")
    for e in mine:
        print(f"  - {e.get('created_at')} | -> {e.get('to')} | {e.get('last_event')} | "
              f"{(e.get('subject') or '')[:70]}")

    delivered = {"sent", "delivered", "opened", "clicked"}
    despacho = [e for e in mine if "confirmá la recepción" in (e.get("subject") or "")
                or "confirm" in (e.get("subject") or "").lower()]
    check(len(despacho) >= 3, "salieron los 3 emails de despacho al receptor", f"{len(despacho)}")
    check(all(e.get("last_event") in delivered for e in despacho),
          "ninguno de los emails de despacho rebotó",
          ", ".join(sorted({e.get("last_event") for e in despacho})))
    check(all(str(e.get("from", "")).endswith("<notificaciones@mail.friese.com.ar>")
              for e in mine),
          "todos salen del dominio propio verificado (no onboarding@resend.dev)")

    queja = [e for e in mine if "queja" in (e.get("subject") or "").lower()]
    check(len(queja) >= 1, "salió el aviso de queja al admin de la empresa", f"{len(queja)}")
    check(any(COMPANY_ADMIN_EMAIL in (e.get("to") or []) for e in queja),
          "el aviso de queja fue al email del admin de la empresa")

    cierre = [e for e in mine if "cerrado" in (e.get("subject") or "").lower()]
    check(len(cierre) >= 1, "salió el email de cierre automático al receptor", f"{len(cierre)}")

    # El contenido de CADA email de despacho tiene que traer el link único del
    # remito que anuncia: se saca el número del asunto y se compara contra el
    # public_token que ese remito tiene en la base.
    import re
    for email in despacho:
        eid = email["id"]
        num = re.search(r"Remito #(\d+)", email.get("subject") or "")
        if not num:
            continue
        req = urllib.request.Request(
            f"https://api.resend.com/emails/{eid}",
            headers={"Authorization": f"Bearer {settings.RESEND_API_KEY}",
                     "User-Agent": "friese-smoke66/1.0", "Accept": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=30) as resp:
            detail = json.loads(resp.read().decode())
        html = detail.get("html") or ""
        shipment = Shipment.objects.filter(pk=int(num.group(1))).first()
        if shipment is None:
            continue
        link = f"{FRONTEND}/remito/{shipment.public_token}"
        check(link in html,
              f"el email del remito #{shipment.pk} trae su link único de producción",
              link)
    return summary("emails")


def phase_cleanup():
    """Borra TODO lo que creó el smoke test (base y R2)."""
    state = load()
    company_id = state.get("company_id")

    borrados = {}
    if company_id:
        shipment_ids = list(Shipment.objects.filter(company_id=company_id)
                            .values_list("id", flat=True))
        # Primero R2: los objetos se borran por su key, que sale del file_url.
        from shipments.storage import get_r2_client
        client = get_r2_client()
        base = settings.R2_PUBLIC_BASE_URL.rstrip("/") + "/"
        r2 = 0
        for url in Evidence.objects.filter(shipment_id__in=shipment_ids).values_list(
                "file_url", flat=True):
            if url.startswith(base):
                client.delete_object(Bucket=settings.R2_BUCKET_NAME, Key=url[len(base):])
                r2 += 1
        borrados["fotos en R2"] = r2

        borrados["evidence"] = Evidence.objects.filter(shipment_id__in=shipment_ids).delete()[0]
        borrados["items"] = ShipmentItem.objects.filter(shipment_id__in=shipment_ids).delete()[0]
        borrados["remitos"] = Shipment.objects.filter(company_id=company_id).delete()[0]
        borrados["productos"] = Product.objects.filter(company_id=company_id).delete()[0]
        borrados["invitaciones"] = OperatorInvite.objects.filter(company_id=company_id).delete()[0]
        borrados["usagelog"] = UsageLog.objects.filter(company_id=company_id).delete()[0]
        borrados["usuarios"] = User.objects.filter(company_id=company_id).delete()[0]
        borrados["empresa"] = Company.objects.filter(pk=company_id).delete()[0]

    if state.get("root_id"):
        borrados["superusuario temporal"] = User.objects.filter(pk=state["root_id"]).delete()[0]

    for k, v in borrados.items():
        print(f"  borrado {k}: {v}")

    check(not Company.objects.filter(pk=company_id).exists(), "la empresa de prueba ya no existe")
    check(not User.objects.filter(username__startswith="smoke66").exists()
          and not User.objects.filter(username__startswith=TAG.lower()).exists(),
          "no quedó ningún usuario del smoke test")
    check(not User.objects.filter(pk=state.get("root_id", 0)).exists(),
          "el superusuario temporal fue eliminado")

    print("\n  Estado final de la base:")
    print("   companies:", Company.objects.count(), "| users:", User.objects.count(),
          "| products:", Product.objects.count(), "| shipments:", Shipment.objects.count(),
          "| evidence:", Evidence.objects.count(), "| invites:", OperatorInvite.objects.count())
    return summary("cleanup")


PHASES = {
    "setup": phase_setup, "admin": phase_admin, "operator": phase_operator,
    "receiver": phase_receiver, "expire": phase_expire, "cron": phase_cron,
    "reminder_setup": phase_reminder_setup, "reminder_check": phase_reminder_check,
    "emails": phase_emails, "cleanup": phase_cleanup,
}

if __name__ == "__main__":
    if len(sys.argv) != 2 or sys.argv[1] not in PHASES:
        print("Fases:", ", ".join(PHASES))
        sys.exit(2)
    print(f"=== Fase «{sys.argv[1]}» contra {BACKEND} ===")
    sys.exit(PHASES[sys.argv[1]]())
