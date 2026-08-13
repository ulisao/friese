"""Tarea 7.4 — verificación de la recuperación de contraseña, de punta a punta.

Corre contra el Django local (con el frontend apuntado al dev server de Vite) y
contra la cuenta REAL de Resend: los emails se mandan de verdad, se leen de vuelta
por la API de Resend y el link que se prueba es el que viajó en el email, no uno
armado acá.

Qué cubre:
  1. contrato de los dos endpoints (respuesta genérica, 400s, campos)
  2. el email real: llega, dice lo que tiene que decir y trae el link
  3. la confirmación: cambia la contraseña, el link sirve UNA vez y cierra las
     sesiones abiertas del usuario
  4. el admin de empresa: el link del login del panel, y el reset completo con
     login posterior AL PANEL
  5. el rate limiting por IP
  6. el flujo del operador en el navegador, de punta a punta

Los datos de prueba (empresa, usuarios) se borran al final, pasen o fallen los
checks: la base de desarrollo es la misma Supabase de producción.
"""

import os
import re
import secrets
import subprocess
import sys
import time
from datetime import timedelta

import django
import requests

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE_DIR)
sys.path.insert(0, HERE)
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
django.setup()

from django.conf import settings  # noqa: E402
from django.contrib.auth.tokens import (  # noqa: E402
    PasswordResetTokenGenerator,
    default_token_generator,
)
from django.core.cache import cache  # noqa: E402
from django.utils import timezone  # noqa: E402
from django.utils.encoding import force_bytes, force_str  # noqa: E402
from django.utils.http import urlsafe_base64_decode, urlsafe_base64_encode  # noqa: E402

from companies.models import Company, UsageLog  # noqa: E402
from users.emails import build_reset_link  # noqa: E402
from users.models import OperatorInvite, User  # noqa: E402
from users.password_reset import usuarios_para  # noqa: E402

from browser import Browser  # noqa: E402
from e2e import check, summary  # noqa: E402

PYTHON = os.path.join(BASE_DIR, "venv", "Scripts", "python.exe")
FRONT = "http://localhost:5173"
API = "http://127.0.0.1:8000/api"
ADMIN = "http://127.0.0.1:8000/admin"
TAG = "SMOKE74"
CASILLA_OPERADOR = "ulisessbaretta+smoke74op@gmail.com"
CASILLA_ADMIN = "ulisessbaretta+smoke74admin@gmail.com"
ASUNTO = "Recuperá tu contraseña de Friese"
# Clave del contador del throttle de esta IP (formato de DRF).
CLAVE_THROTTLE = "throttle_password_reset_127.0.0.1"


def resend_get(path):
    """GET a la API de Resend con la key del proyecto (nunca se imprime)."""
    r = requests.get(
        f"https://api.resend.com{path}",
        headers={"Authorization": f"Bearer {settings.RESEND_API_KEY}"},
        timeout=30,
    )
    return r.status_code, (r.json() if r.headers.get("content-type", "").startswith("application/json") else r.text)


def buscar_email(casilla, desde, timeout=90):
    """Devuelve el email de recuperación más nuevo mandado a `casilla`.

    Se filtra por fecha de creación para no tomar el de una corrida anterior.
    """
    limite = time.time() + timeout
    while time.time() < limite:
        status, data = resend_get("/emails")
        if status == 200 and isinstance(data, dict):
            for item in data.get("data") or []:
                if casilla not in (item.get("to") or []):
                    continue
                if ASUNTO not in (item.get("subject") or ""):
                    continue
                creado = str(item.get("created_at") or "")
                if creado >= desde:
                    return item
        time.sleep(3)
    return None


def esperar_delivered(email_id, timeout=120):
    """Espera a que Resend confirme la entrega. Devuelve el email completo."""
    limite = time.time() + timeout
    ultimo = None
    while time.time() < limite:
        status, data = resend_get(f"/emails/{email_id}")
        if status == 200 and isinstance(data, dict):
            ultimo = data
            if data.get("last_event") == "delivered":
                return data
        time.sleep(4)
    return ultimo


def link_del_email(email):
    """Saca el link de recuperación del cuerpo del email (el que viajó de verdad)."""
    cuerpo = (email.get("text") or "") + " " + (email.get("html") or "")
    encontrados = re.findall(rf"{re.escape(FRONT)}/restablecer/[^\s\"'<>]+", cuerpo)
    return encontrados[0] if encontrados else None


def partes_del_link(link):
    uid, token = link.rstrip("/").split("/restablecer/")[1].split("/")
    return uid, token


def limpiar_throttle():
    """Borra el contador de esta IP: el propio test gasta el cupo que va a probar."""
    cache.delete(CLAVE_THROTTLE)


# El link del email tiene que apuntar al frontend local para poder abrirlo en el
# navegador; en el .env FRONTEND_PUBLIC_URL apunta a producción.
entorno = {**os.environ, "FRONTEND_PUBLIC_URL": FRONT}

procesos = [
    subprocess.Popen([PYTHON, "manage.py", "runserver", "127.0.0.1:8000", "--noreload"],
                     cwd=BASE_DIR, env=entorno,
                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL),
    subprocess.Popen(["npm.cmd", "run", "dev"], cwd=os.path.join(BASE_DIR, "frontend"),
                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL),
]

company = navegador = None
completo = completo_admin = {}
link = None
try:
    for url in (f"{API}/public/shipment/00000000-0000-0000-0000-000000000000/", FRONT):
        limite = time.time() + 90
        while time.time() < limite:
            try:
                requests.get(url, timeout=5)
                break
            except Exception:
                time.sleep(0.5)
        else:
            raise RuntimeError(f"no levantó {url}")

    # --- Datos de prueba ---------------------------------------------------
    company = Company.objects.create(name=f"Recuperos {TAG} SA", email=f"{TAG.lower()}@friese.test")
    clave_vieja = secrets.token_urlsafe(18)
    operador = User.objects.create_user(
        username=f"{TAG.lower()}_op", password=clave_vieja, email=CASILLA_OPERADOR,
        company=company, role=User.OPERATOR)
    admin_empresa = User.objects.create_user(
        username=f"{TAG.lower()}_admin", password=secrets.token_urlsafe(18),
        email=CASILLA_ADMIN, company=company, role=User.ADMIN, is_staff=True)
    sin_email = User.objects.create_user(
        username=f"{TAG.lower()}_sinmail", password=secrets.token_urlsafe(18),
        company=company, role=User.OPERATOR)
    inactivo = User.objects.create_user(
        username=f"{TAG.lower()}_baja", password=secrets.token_urlsafe(18),
        email=f"{TAG.lower()}baja@friese.test", company=company, role=User.OPERATOR,
        is_active=False)

    print("\n=== 1. A quién le llega el link (reglas de búsqueda) ===")
    check([u.pk for u in usuarios_para(operador.username)] == [operador.pk],
          "por nombre de usuario encuentra al operador")
    check([u.pk for u in usuarios_para(CASILLA_OPERADOR)] == [operador.pk],
          "por email encuentra al mismo operador")
    check([u.pk for u in usuarios_para(operador.username.upper())] == [operador.pk],
          "no distingue mayúsculas de minúsculas")
    check(usuarios_para(sin_email.username) == [],
          "el operador SIN email queda afuera (no hay dónde mandarle nada)")
    check(usuarios_para(inactivo.username) == [], "el usuario dado de baja queda afuera")
    check(usuarios_para(f"{TAG}_no_existe") == [], "un usuario inexistente no devuelve nada")
    check(usuarios_para("") == [], "el texto vacío no devuelve nada")

    print("\n=== 2. Contrato del endpoint de pedido ===")
    limpiar_throttle()
    momento = (timezone.now() - timedelta(minutes=2)).strftime("%Y-%m-%d %H:%M:%S")

    r = requests.post(f"{API}/auth/password-reset/", json={"identifier": operador.username}, timeout=30)
    check(r.status_code == 200, "pedido con un usuario real -> 200", f"HTTP {r.status_code}")
    respuesta_real = r.json().get("detail", "")
    check("link" in respuesta_real.lower(), "responde el mensaje genérico", respuesta_real[:60])

    r = requests.post(f"{API}/auth/password-reset/", json={"identifier": f"{TAG}_no_existe"}, timeout=30)
    check(r.status_code == 200 and r.json().get("detail") == respuesta_real,
          "un usuario que NO existe responde EXACTAMENTE lo mismo (no delata quién existe)",
          f"HTTP {r.status_code}")

    r = requests.post(f"{API}/auth/password-reset/", json={"identifier": sin_email.username}, timeout=30)
    check(r.status_code == 200 and r.json().get("detail") == respuesta_real,
          "un usuario sin email responde lo mismo")

    r = requests.post(f"{API}/auth/password-reset/", json={}, timeout=30)
    check(r.status_code == 400, "pedido sin el campo identifier -> 400", f"HTTP {r.status_code}")

    print("\n=== 3. El email real (leído de vuelta desde Resend) ===")
    email = buscar_email(CASILLA_OPERADOR, momento)
    check(email is not None, f"llegó un email de recuperación a {CASILLA_OPERADOR}")
    if email:
        completo = esperar_delivered(email["id"]) or {}
        check(completo.get("last_event") == "delivered",
              "Resend lo confirma ENTREGADO", str(completo.get("last_event")))
        check(settings.RESEND_FROM_EMAIL in (completo.get("from") or ""),
              "sale del dominio verificado", str(completo.get("from")))
        cuerpo = (completo.get("text") or "") + (completo.get("html") or "")
        check(operador.username in cuerpo, "el email dice de qué usuario es")
        check("24 horas" in cuerpo, "avisa que el link vence en 24 horas")
        check("una sola vez" in cuerpo.lower() or "UNA sola vez" in cuerpo,
              "avisa que el link sirve una sola vez")
        check(FRONT in cuerpo, "el link apunta al frontend configurado", FRONT)

        link = link_del_email(completo)
        check(link is not None, "el email trae el link de recuperación")

    print("\n=== 4. La contraseña nueva ===")
    # Sesión abierta ANTES del reset: tiene que quedar muerta después.
    sesion = requests.Session()
    r = sesion.post(f"{API}/auth/login/", json={"username": operador.username, "password": clave_vieja}, timeout=30)
    check(r.status_code == 200, "el operador entra con la contraseña vieja", f"HTTP {r.status_code}")
    r = sesion.post(f"{API}/auth/refresh/", timeout=30)
    check(r.status_code == 200, "y su sesión refresca bien antes del cambio")

    uid, token = partes_del_link(link)
    clave_nueva = secrets.token_urlsafe(18)

    r = requests.post(f"{API}/auth/password-reset/confirm/",
                      json={"uid": uid, "token": token, "password": "1234"}, timeout=30)
    check(r.status_code == 400, "una contraseña débil se rechaza -> 400", f"HTTP {r.status_code}")
    check("corta" in str(r.json()).lower() or "común" in str(r.json()).lower(),
          "y explica por qué", str(r.json())[:90])

    r = requests.post(f"{API}/auth/password-reset/confirm/",
                      json={"uid": uid, "token": token[:-3] + "xyz", "password": clave_nueva}, timeout=30)
    check(r.status_code == 400, "un token manipulado se rechaza -> 400", f"HTTP {r.status_code}")

    r = requests.post(f"{API}/auth/password-reset/confirm/",
                      json={"uid": "xxxx", "token": token, "password": clave_nueva}, timeout=30)
    check(r.status_code == 400, "un uid inventado se rechaza -> 400", f"HTTP {r.status_code}")

    r = requests.post(f"{API}/auth/password-reset/confirm/",
                      json={"uid": uid, "token": token, "password": clave_nueva}, timeout=30)
    check(r.status_code == 200, "el link REAL del email cambia la contraseña -> 200", f"HTTP {r.status_code}")

    r = requests.post(f"{API}/auth/login/", json={"username": operador.username, "password": clave_nueva}, timeout=30)
    check(r.status_code == 200, "entra con la contraseña NUEVA", f"HTTP {r.status_code}")
    r = requests.post(f"{API}/auth/login/", json={"username": operador.username, "password": clave_vieja}, timeout=30)
    check(r.status_code == 401, "la contraseña VIEJA ya no sirve", f"HTTP {r.status_code}")

    r = requests.post(f"{API}/auth/password-reset/confirm/",
                      json={"uid": uid, "token": token, "password": secrets.token_urlsafe(18)}, timeout=30)
    check(r.status_code == 400, "el mismo link una segunda vez NO sirve -> 400", f"HTTP {r.status_code}")

    r = sesion.post(f"{API}/auth/refresh/", timeout=30)
    check(r.status_code == 401, "la sesión que estaba abierta quedó cerrada", f"HTTP {r.status_code}")

    print("\n=== 5. El admin de empresa ===")
    limpiar_throttle()
    r = requests.get(f"{ADMIN}/login/", timeout=30)
    check("/admin/password_reset/" in r.text,
          "el login del panel muestra el link de «¿perdiste tu contraseña?»")
    r = requests.get(f"{ADMIN}/password_reset/", timeout=30, allow_redirects=False)
    check(r.status_code == 302 and r.headers.get("Location", "").startswith(f"{FRONT}/recuperar-contrasena"),
          "y ese link lleva a la MISMA pantalla del operador",
          f"HTTP {r.status_code} -> {r.headers.get('Location')}")

    momento = (timezone.now() - timedelta(minutes=2)).strftime("%Y-%m-%d %H:%M:%S")
    r = requests.post(f"{API}/auth/password-reset/", json={"identifier": CASILLA_ADMIN}, timeout=30)
    check(r.status_code == 200, "el admin pide el link con su email -> 200", f"HTTP {r.status_code}")

    email_admin = buscar_email(CASILLA_ADMIN, momento)
    check(email_admin is not None, f"le llega el email a {CASILLA_ADMIN}")
    completo_admin = (esperar_delivered(email_admin["id"]) or {}) if email_admin else {}
    check(completo_admin.get("last_event") == "delivered", "Resend lo confirma ENTREGADO",
          str(completo_admin.get("last_event")))
    cuerpo_admin = (completo_admin.get("text") or "") + (completo_admin.get("html") or "")
    check("/admin/" in cuerpo_admin,
          "al admin el email le dice que vuelva a entrar POR EL PANEL (al operador no)")
    check("/admin/" not in ((completo.get("text") or "") + (completo.get("html") or "")),
          "el email del operador NO menciona el panel")

    uid_admin, token_admin = partes_del_link(link_del_email(completo_admin))
    clave_admin = secrets.token_urlsafe(18)
    r = requests.post(f"{API}/auth/password-reset/confirm/",
                      json={"uid": uid_admin, "token": token_admin, "password": clave_admin}, timeout=30)
    check(r.status_code == 200, "el admin cambia su contraseña -> 200", f"HTTP {r.status_code}")

    sesion_admin = requests.Session()
    pagina = sesion_admin.get(f"{ADMIN}/login/", timeout=30)
    csrf = re.search(r'name="csrfmiddlewaretoken" value="([^"]+)"', pagina.text).group(1)
    r = sesion_admin.post(f"{ADMIN}/login/", timeout=30, allow_redirects=False,
                          data={"username": admin_empresa.username, "password": clave_admin,
                                "csrfmiddlewaretoken": csrf, "next": "/admin/"},
                          headers={"Referer": f"{ADMIN}/login/"})
    check(r.status_code == 302, "y entra AL PANEL con la contraseña nueva", f"HTTP {r.status_code}")

    print("\n=== 6. Rate limiting por IP ===")
    limpiar_throttle()
    cupo = int(settings.REST_FRAMEWORK["DEFAULT_THROTTLE_RATES"]["password_reset"].split("/")[0])
    codigos = [
        requests.post(f"{API}/auth/password-reset/",
                      json={"identifier": f"{TAG}_no_existe"}, timeout=30).status_code
        for _ in range(cupo + 2)
    ]
    check(codigos[:cupo] == [200] * cupo, f"las primeras {cupo} pasan", str(codigos[:5]))
    check(codigos[cupo] == 429, f"la número {cupo + 1} corta con 429", str(codigos[cupo]))
    limpiar_throttle()
    r = requests.post(f"{API}/auth/password-reset/confirm/",
                      json={"uid": "x", "token": "x", "password": "x"}, timeout=30)
    check(r.status_code == 400,
          "borrado el contador, el endpoint vuelve a atender (el cupo es por ventana)",
          f"HTTP {r.status_code}")

    print("\n=== 7. El flujo completo del operador en el navegador ===")
    limpiar_throttle()
    momento = (timezone.now() - timedelta(minutes=2)).strftime("%Y-%m-%d %H:%M:%S")
    navegador = Browser()
    navegador.goto(f"{FRONT}/login")
    navegador.wait("document.querySelector('a[href=\"/recuperar-contrasena\"]')",
                   label="link de recuperación en el login")
    check(True, "el login del operador ofrece «¿Olvidaste tu contraseña?»")
    navegador.click('a[href="/recuperar-contrasena"]')
    navegador.wait("document.querySelector('#identifier')", label="pantalla de recuperación")
    navegador.shot("74-recuperar")

    navegador.fill("#identifier", operador.username)
    navegador.click('button[type="submit"]')
    navegador.wait("document.querySelector('[data-testid=\"reset-sent\"]')",
                   label="confirmación del envío")
    check(True, "pide el link desde la app y muestra la confirmación")
    navegador.shot("74-enviado")

    email_ui = buscar_email(CASILLA_OPERADOR, momento)
    check(email_ui is not None, "el pedido desde la app manda el email igual que por la API")
    link_ui = link_del_email(esperar_delivered(email_ui["id"]) or {})

    navegador.goto(link_ui)
    navegador.wait("document.querySelector('#password')", label="pantalla de contraseña nueva")
    clave_final = secrets.token_urlsafe(18)
    navegador.fill("#password", clave_final)
    navegador.fill("#password-confirm", "otra-cosa-distinta")
    navegador.click('button[type="submit"]')
    navegador.wait("document.querySelector('[data-testid=\"reset-error\"]')",
                   label="error de contraseñas distintas")
    check("no coinciden" in navegador.text('[data-testid="reset-error"]'),
          "avisa si las dos contraseñas no coinciden")

    navegador.fill("#password-confirm", clave_final)
    navegador.click('button[type="submit"]')
    navegador.wait("document.querySelector('[data-testid=\"reset-done\"]')",
                   label="confirmación del cambio")
    check(True, "guarda la contraseña nueva desde el navegador")
    navegador.shot("74-listo")

    navegador.click('a[href="/login"]')
    navegador.wait("document.querySelector('#username')", label="login")
    navegador.fill("#username", operador.username)
    navegador.fill("#password", clave_final)
    navegador.click('button[type="submit"]')
    navegador.wait("location.pathname === '/'", label="lista de remitos")
    check(True, "y el operador entra a la app con esa contraseña")
    navegador.shot("74-adentro")

    errores = [e for e in navegador.errores_de_consola() if "favicon" not in e.lower()]
    check(not errores, "sin errores de consola en todo el recorrido", "; ".join(errores)[:150])

    print("\n=== 8. Alta de operador con email (para poder recuperar después) ===")
    invite = OperatorInvite.objects.create(
        company=company, expires_at=timezone.now() + timedelta(days=1))
    nuevo_usuario, nueva_casilla = f"{TAG.lower()}_qr", f"{TAG.lower()}qr@friese.test"
    r = requests.post(f"{API}/auth/register-operator/", timeout=30, json={
        "token": str(invite.token), "username": nuevo_usuario,
        "password": secrets.token_urlsafe(18), "email": nueva_casilla})
    check(r.status_code == 201, "el alta por QR acepta el email -> 201", f"HTTP {r.status_code}")
    creado = User.objects.filter(username=nuevo_usuario).first()
    check(creado is not None and creado.email == nueva_casilla,
          "y queda guardado en el usuario", getattr(creado, "email", None))
    check([u.pk for u in usuarios_para(nueva_casilla)] == [creado.pk],
          "ese operador ya puede recuperar su contraseña solo")

    invite2 = OperatorInvite.objects.create(
        company=company, expires_at=timezone.now() + timedelta(days=1))
    r = requests.post(f"{API}/auth/register-operator/", timeout=30, json={
        "token": str(invite2.token), "username": f"{TAG.lower()}_qr2",
        "password": secrets.token_urlsafe(18)})
    check(r.status_code == 201, "el alta SIN email sigue funcionando (el campo es opcional)",
          f"HTTP {r.status_code}")

    print("\n=== 9. El armado del link y su vencimiento ===")
    # OJO: este proceso lee el .env, no el FRONTEND_PUBLIC_URL que se le pasó al
    # server; por eso se compara contra settings y no contra FRONT.
    base = settings.FRONTEND_PUBLIC_URL.rstrip("/")
    uid_directo = urlsafe_base64_encode(force_bytes(operador.pk))
    check(build_reset_link(uid_directo, "tok") == f"{base}/restablecer/{uid_directo}/tok",
          "el link se arma con FRONTEND_PUBLIC_URL y el formato /restablecer/{uid}/{token}",
          build_reset_link(uid_directo, "tok"))
    check(force_str(urlsafe_base64_decode(uid_directo)) == str(operador.pk),
          "el uid del link decodifica al usuario correcto")

    # Vencimiento: se le miente la hora al generador de tokens (es de dónde saca
    # el "ahora" para medir la antigüedad del token).
    class GeneradorEnElFuturo(PasswordResetTokenGenerator):
        horas = 0

        def _now(self):
            return super()._now() + timedelta(hours=self.horas)

    usuario = User.objects.get(pk=operador.pk)
    token_fresco = default_token_generator.make_token(usuario)
    horas_de_vida = settings.PASSWORD_RESET_TIMEOUT // 3600
    check(horas_de_vida == 24, "el link vive 24hs (PASSWORD_RESET_TIMEOUT)", str(horas_de_vida))

    casi = GeneradorEnElFuturo()
    casi.horas = horas_de_vida - 1
    check(casi.check_token(usuario, token_fresco),
          f"a las {horas_de_vida - 1} horas el link todavía sirve")

    tarde = GeneradorEnElFuturo()
    tarde.horas = horas_de_vida + 1
    check(not tarde.check_token(usuario, token_fresco),
          f"a las {horas_de_vida + 1} horas ya venció")

finally:
    if navegador:
        navegador.close()
    limpiar_throttle()
    if company:
        OperatorInvite.objects.filter(company=company).delete()
        User.objects.filter(company=company).delete()
        UsageLog.objects.filter(company=company).delete()
        Company.objects.filter(pk=company.pk).delete()
        print("\nDatos de prueba borrados.")
    for proc in procesos:
        proc.terminate()
    for proc in procesos:
        try:
            proc.wait(timeout=10)
        except Exception:
            proc.kill()

sys.exit(summary("Tarea 7.4 — recuperación de contraseña"))
