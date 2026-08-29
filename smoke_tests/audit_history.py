"""Criterio de aceptación de la 8.2 — el historial de cambios (django-simple-history).

Edita registros de prueba DESDE EL DJANGO ADMIN, por HTTP y contra los formularios
reales, y comprueba que cada cambio deja su fila de historial con qué cambió, quién
lo cambió, cuándo, y el valor anterior. Después verifica que ese historial es de solo
lectura y que no se filtra entre empresas.

    python smoke_tests/audit_history.py

Levanta su propio server local contra la base de siempre, crea sus datos con la marca
SMOKE82 —dos empresas, para poder probar el aislamiento— y los borra al final, incluidas
las filas de historial que generó (que sobreviven al borrado de su objeto, justamente
porque un historial que se borra con el registro no serviría de nada).
"""

import os
import secrets
import subprocess
import sys
import time
from html.parser import HTMLParser

import django
import requests

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE_DIR)
sys.path.insert(0, HERE)
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
django.setup()

from django.utils import timezone  # noqa: E402

from catalog.models import Product  # noqa: E402
from companies.models import Company  # noqa: E402
from shipments.models import Evidence, Shipment, ShipmentItem  # noqa: E402
from users.groups import ensure_company_admin_group  # noqa: E402
from users.models import User  # noqa: E402

from browser import Browser  # noqa: E402
from e2e import borrar_historial, check, summary  # noqa: E402

PYTHON = os.path.join(BASE_DIR, "venv", "Scripts", "python.exe")
PUERTO = 8024
LOCAL = f"http://127.0.0.1:{PUERTO}"
API = f"{LOCAL}/api"
ADMIN = f"{LOCAL}/admin"
TAG = "SMOKE82"


# --- Formularios del admin ---------------------------------------------------
# El criterio de la tarea es "editar desde el Django Admin", así que se editan los
# formularios de verdad y no el modelo por el ORM: es el camino que tiene que dejar
# huella. Para reenviar un formulario del admin hay que devolver TODOS sus campos
# (incluidos los management forms de los inlines), así que se leen de la pantalla.

class LectorDeFormulario(HTMLParser):
    """Saca los pares (name, value) que un navegador enviaría de la pantalla."""

    IGNORAR = {"csrfmiddlewaretoken", "q", "next", "_selected_action"}

    def __init__(self):
        super().__init__()
        self.campos = []
        self._select = None
        self._textarea = None
        self._buffer = ""

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        nombre = a.get("name")
        if tag == "input":
            tipo = (a.get("type") or "text").lower()
            if not nombre or nombre in self.IGNORAR:
                return
            if tipo in ("submit", "button", "reset", "image", "file"):
                return
            if tipo in ("checkbox", "radio"):
                if "checked" not in a:
                    return
                self.campos.append((nombre, a.get("value", "on")))
                return
            # Un input de texto vacío se renderiza SIN atributo value: vale "", no "on"
            # (con "on" el admin rechaza los campos de fecha/hora que están en blanco).
            self.campos.append((nombre, a.get("value", "")))
        elif tag == "select":
            self._select = nombre if nombre not in self.IGNORAR else None
        elif tag == "option":
            if self._select and "selected" in a:
                self.campos.append((self._select, a.get("value", "")))
        elif tag == "textarea":
            self._textarea = nombre if nombre not in self.IGNORAR else None
            self._buffer = ""

    def handle_data(self, data):
        if self._textarea:
            self._buffer += data

    def handle_endtag(self, tag):
        if tag == "select":
            self._select = None
        elif tag == "textarea":
            if self._textarea:
                self.campos.append((self._textarea, self._buffer))
            self._textarea = None


def entrar_al_admin(usuario, password):
    """Sesión con el login del Django Admin ya hecho."""
    s = requests.Session()
    s.get(f"{ADMIN}/login/", timeout=30).raise_for_status()
    r = s.post(f"{ADMIN}/login/",
               data={"username": usuario, "password": password,
                     "csrfmiddlewaretoken": s.cookies["csrftoken"], "next": "/admin/"},
               headers={"Referer": f"{ADMIN}/login/"},
               allow_redirects=False, timeout=30)
    return s, r


def guardar(sesion, path, cambios):
    """Reenvía un formulario del admin con `cambios` aplicados. Devuelve la respuesta."""
    url = f"{ADMIN}{path}"
    pantalla = sesion.get(url, timeout=30)
    pantalla.raise_for_status()
    lector = LectorDeFormulario()
    lector.feed(pantalla.text)

    datos = {}
    for nombre, valor in lector.campos:
        datos.setdefault(nombre, []).append(valor)
    datos = {k: (v[0] if len(v) == 1 else v) for k, v in datos.items()}
    datos.update(cambios)
    datos["csrfmiddlewaretoken"] = sesion.cookies["csrftoken"]
    datos["_save"] = "Grabar"

    r = sesion.post(url, data=datos, headers={"Referer": url},
                    allow_redirects=False, timeout=60)
    if r.status_code == 200:
        # El admin re-renderiza el form con los errores en vez de redirigir.
        import re
        errores = re.findall(r'<ul class="errorlist[^"]*"[^>]*>(.*?)</ul>', r.text, re.S)
        if errores:
            print("    errores del formulario:", " | ".join(
                re.sub(r"<[^>]+>", " ", e).strip() for e in errores)[:400])
    return r


def ultimo(modelo, **filtro):
    """Última fila de historial de un objeto (el historial ordena por fecha desc)."""
    return modelo.history.filter(**filtro).first()


servidor = subprocess.Popen(
    [PYTHON, "manage.py", "runserver", f"127.0.0.1:{PUERTO}", "--noreload"],
    cwd=BASE_DIR, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

nav = None
empresas = []
usuarios = []
try:
    limite = time.time() + 90
    while time.time() < limite:
        try:
            requests.get(f"{ADMIN}/login/", timeout=5)
            break
        except Exception:
            time.sleep(0.4)
    else:
        raise RuntimeError("no levantó el backend")

    # --- Datos de prueba --------------------------------------------------
    pass_super = secrets.token_urlsafe(18)
    superadmin = User.objects.create_superuser(
        username=f"{TAG.lower()}_root", password=pass_super,
        email=f"{TAG.lower()}root@friese.test")
    usuarios.append(superadmin)

    empresa = Company.objects.create(name=f"Fletes {TAG} SA",
                                     email=f"{TAG.lower()}@friese.test")
    ajena = Company.objects.create(name=f"Ajena {TAG} SRL",
                                   email=f"{TAG.lower()}b@friese.test")
    empresas += [empresa, ajena]

    pass_admin = secrets.token_urlsafe(18)
    admin_empresa = User.objects.create_user(
        username=f"{TAG.lower()}_admin", password=pass_admin, company=empresa,
        role=User.ADMIN, is_staff=True, email=f"{TAG.lower()}a@friese.test")
    admin_empresa.groups.add(ensure_company_admin_group())
    pass_op = secrets.token_urlsafe(18)
    operador = User.objects.create_user(
        username=f"{TAG.lower()}_op", password=pass_op, company=empresa,
        role=User.OPERATOR)
    usuarios += [admin_empresa, operador]

    producto = Product.objects.create(company=empresa, name=f"Bolsas {TAG}", unit="bolsas")
    remito = Shipment.objects.create(company=empresa, operator=operador,
                                     receiver_name=f"Depósito {TAG}",
                                     receiver_email="nadie@friese.test")
    item = ShipmentItem.objects.create(shipment=remito, product=producto, quantity="10.00")
    evidencia = Evidence.objects.create(shipment=remito, type=Evidence.DISPATCH,
                                        uploaded_by=operador,
                                        file_url="https://ejemplo.test/foto-smoke82.jpg",
                                        file_hash="a" * 64)

    op_ajeno = User.objects.create_user(username=f"{TAG.lower()}_opb", password=pass_op,
                                        company=ajena, role=User.OPERATOR)
    usuarios.append(op_ajeno)
    remito_ajeno = Shipment.objects.create(company=ajena, operator=op_ajeno,
                                           receiver_name=f"Secreto de la otra {TAG}")

    sesion, r = entrar_al_admin(f"{TAG.lower()}_root", pass_super)
    check(r.status_code == 302, "el superadmin entra al panel", f"HTTP {r.status_code}")

    # --- 1. Editar un remito desde el admin deja historial -----------------
    print("\n=== 1. Editar desde el Django Admin ===")
    antes = Shipment.history.filter(id=remito.pk).count()
    momento = timezone.now()
    r = guardar(sesion, f"/shipments/shipment/{remito.pk}/change/",
                {"receiver_name": f"Depósito {TAG} CORREGIDO"})
    check(r.status_code == 302, "el form del remito guarda", f"HTTP {r.status_code}")

    filas = Shipment.history.filter(id=remito.pk).count()
    check(filas == antes + 1, "la edición del remito dejó UNA fila de historial",
          f"{antes} -> {filas}")
    fila = ultimo(Shipment, id=remito.pk)
    check(fila.history_type == "~", "la fila queda marcada como modificación",
          fila.history_type)
    check(fila.history_user_id == superadmin.pk,
          "el historial guarda QUIÉN lo cambió (el usuario logueado en el admin)",
          str(fila.history_user))
    check(fila.history_date >= momento, "el historial guarda CUÁNDO se cambió",
          str(fila.history_date))
    check(fila.receiver_name == f"Depósito {TAG} CORREGIDO",
          "la fila guarda el valor nuevo", fila.receiver_name)

    delta = fila.diff_against(fila.prev_record)
    cambiados = {c.field: (c.old, c.new) for c in delta.changes}
    check(list(cambiados) == ["receiver_name"],
          "el historial dice QUÉ campo cambió, y solo ese", list(cambiados))
    check(cambiados["receiver_name"][0] == f"Depósito {TAG}",
          "el historial guarda el VALOR ANTERIOR", cambiados["receiver_name"][0])

    # --- 2. Los otros tres modelos de la tarea -----------------------------
    print("\n=== 2. Empresa, usuario y evidencia ===")
    r = guardar(sesion, f"/companies/company/{empresa.pk}/change/",
                {"plan": "crecimiento", "trial_shipments_remaining": "3"})
    check(r.status_code == 302, "el form de la empresa guarda", f"HTTP {r.status_code}")
    fila = ultimo(Company, id=empresa.pk)
    cambiados = {c.field: (c.old, c.new)
                 for c in fila.diff_against(fila.prev_record).changes}
    check(fila.history_user_id == superadmin.pk and set(cambiados) ==
          {"plan", "trial_shipments_remaining"},
          "la empresa registra el cambio de plan y de trial, con su autor", cambiados)
    check(cambiados["trial_shipments_remaining"] == (10, 3),
          "con el valor anterior y el nuevo", cambiados["trial_shipments_remaining"])

    r = guardar(sesion, f"/users/user/{operador.pk}/change/", {"is_active": ""})
    check(r.status_code == 302, "el form del usuario guarda", f"HTTP {r.status_code}")
    fila = ultimo(User, id=operador.pk)
    cambiados = {c.field: (c.old, c.new)
                 for c in fila.diff_against(fila.prev_record).changes}
    check(fila.history_user_id == superadmin.pk and cambiados.get("is_active") == (True, False),
          "dar de baja a un operador queda registrado, con quién lo hizo", cambiados)

    r = guardar(sesion, f"/shipments/evidence/{evidencia.pk}/change/",
                {"file_url": "https://ejemplo.test/OTRA-foto.jpg"})
    check(r.status_code == 302, "el form de la evidencia guarda", f"HTTP {r.status_code}")
    fila = ultimo(Evidence, id=evidencia.pk)
    cambiados = {c.field: (c.old, c.new)
                 for c in fila.diff_against(fila.prev_record).changes}
    check(cambiados.get("file_url", ("", ""))[0] == "https://ejemplo.test/foto-smoke82.jpg",
          "cambiarle la foto a una evidencia deja el file_url anterior a la vista",
          cambiados.get("file_url"))
    check(fila.file_hash == "a" * 64,
          "la fila de historial arrastra también el file_hash de la 8.1", fila.file_hash)

    # El ítem se edita desde el inline de la ficha del remito, que es como se toca
    # de verdad: la cantidad despachada no vive en Shipment sino en ShipmentItem.
    r = guardar(sesion, f"/shipments/shipment/{remito.pk}/change/",
                {"items-0-quantity": "999.00"})
    check(r.status_code == 302, "el inline de ítems guarda", f"HTTP {r.status_code}")
    fila = ultimo(ShipmentItem, id=item.pk)
    cambiados = {c.field: (str(c.old), str(c.new))
                 for c in fila.diff_against(fila.prev_record).changes}
    check(cambiados.get("quantity") == ("10.00", "999.00"),
          "cambiar la cantidad desde el inline del remito queda registrado", cambiados)

    # --- 3. El historial también sigue a la API, no solo al admin ----------
    print("\n=== 3. Cambios desde la API del operador ===")
    User.objects.filter(pk=operador.pk).update(is_active=True)  # se dio de baja arriba
    token = requests.post(f"{API}/auth/login/",
                          json={"username": f"{TAG.lower()}_op", "password": pass_op},
                          timeout=30)
    check(token.status_code == 200, "el operador entra por la API", f"HTTP {token.status_code}")
    auth = {"Authorization": f"Bearer {token.json()['access']}"}
    nuevo = requests.post(f"{API}/shipments/", headers=auth,
                          json={"receiver_name": f"Alta por API {TAG}"}, timeout=30)
    check(nuevo.status_code == 201, "el operador crea un remito", f"HTTP {nuevo.status_code}")
    fila = ultimo(Shipment, id=nuevo.json()["id"])
    check(fila is not None and fila.history_type == "+",
          "el alta por la API deja su fila de historial")
    check(fila.history_user_id == operador.pk,
          "y queda a nombre del operador autenticado por JWT (no del admin)",
          str(fila.history_user))

    # El despacho es EL momento del producto: es el que sella el remito. Va por
    # `shipment.save()`, así que sí deja fila (a diferencia de los UPDATE de abajo).
    # Sin receiver_email para no disparar el envío al receptor (shipments/emails.py).
    r = requests.patch(f"{API}/shipments/{nuevo.json()['id']}/dispatch/",
                       headers=auth, timeout=120)
    check(r.status_code == 200, "el operador despacha el remito", f"HTTP {r.status_code}")
    fila = ultimo(Shipment, id=nuevo.json()["id"])
    cambiados = {c.field for c in fila.diff_against(fila.prev_record).changes}
    check(fila.history_user_id == operador.pk and "status" in cambiados,
          "el despacho queda registrado a nombre del operador que lo hizo",
          f"{fila.history_user} / {sorted(cambiados)}")

    # Límite CONOCIDO y documentado (ver PROGRESS.md, tarea 8.2): las transiciones
    # que el producto hace con un UPDATE de queryset no pasan por save() y por lo
    # tanto no dejan fila. Se fija acá para que quede a la vista y no se descubra
    # el día que haga falta.
    antes = Shipment.history.filter(id=remito.pk).count()
    Shipment.objects.filter(pk=remito.pk).update(status=Shipment.ACCEPTED)
    check(Shipment.history.filter(id=remito.pk).count() == antes,
          "LIMITE CONOCIDO: un UPDATE de queryset (cierre automático, accept del "
          "receptor) no deja fila — ver PROGRESS.md 8.2")

    # --- 4. El historial es de solo lectura --------------------------------
    print("\n=== 4. El historial no se puede borrar ni editar ===")
    for modelo in ("historicalshipment", "historicalevidence"):
        r = sesion.get(f"{ADMIN}/shipments/{modelo}/", allow_redirects=False, timeout=30)
        check(r.status_code == 404,
              f"el historial no tiene pantalla propia en el admin ({modelo})",
              f"HTTP {r.status_code}")

    version = Shipment.history.filter(id=remito.pk).last()  # la más vieja
    detalle = f"/shipments/shipment/{remito.pk}/history/{version.history_id}/"
    r = sesion.get(f"{ADMIN}{detalle}", timeout=30)
    check(r.status_code == 200, "la ficha de una versión vieja se puede consultar",
          f"HTTP {r.status_code}")
    check("Revert" not in r.text and "Revertir" not in r.text,
          "sin botón de revertir (SIMPLE_HISTORY_REVERT_DISABLED)")
    r = sesion.post(f"{ADMIN}{detalle}",
                    data={"csrfmiddlewaretoken": sesion.cookies["csrftoken"],
                          "receiver_name": "REVERTIDO A MANO", "status": "draft"},
                    headers={"Referer": f"{ADMIN}{detalle}"},
                    allow_redirects=False, timeout=30)
    check(r.status_code == 403,
          "el POST de revertir se rechaza aunque se arme a mano", f"HTTP {r.status_code}")
    check(Shipment.objects.get(pk=remito.pk).receiver_name == f"Depósito {TAG} CORREGIDO",
          "y el remito quedó como estaba")

    campos = {f.name for f in User.history.model._meta.get_fields()}
    check("password" not in campos,
          "el historial de usuarios NO copia el hash de la contraseña", sorted(campos))

    # --- 5. El historial no se filtra entre empresas ------------------------
    print("\n=== 5. Aislamiento multi-tenant del historial ===")
    sesion_b, r = entrar_al_admin(f"{TAG.lower()}_admin", pass_admin)
    check(r.status_code == 302, "el admin de empresa entra al panel", f"HTTP {r.status_code}")

    r = sesion_b.get(f"{ADMIN}/shipments/shipment/{remito.pk}/history/", timeout=30)
    check(r.status_code == 200 and f"Depósito {TAG}" in r.text,
          "el admin de empresa ve el historial de SU remito", f"HTTP {r.status_code}")
    check(str(superadmin) in r.text,
          "y ahí queda a la vista que lo editó el superadmin de Friese")

    r = sesion_b.get(f"{ADMIN}/shipments/shipment/{remito_ajeno.pk}/history/",
                     allow_redirects=False, timeout=30)
    check(r.status_code == 404,
          "el historial de un remito de OTRA empresa da 404", f"HTTP {r.status_code}")
    check(f"Secreto de la otra {TAG}" not in r.text,
          "y no se filtra nada de esa empresa en la respuesta")

    version_ajena = Shipment.history.filter(id=remito_ajeno.pk).first()
    r = sesion_b.get(f"{ADMIN}/shipments/shipment/{remito_ajeno.pk}/history/"
                     f"{version_ajena.history_id}/", allow_redirects=False, timeout=30)
    check(r.status_code == 404,
          "la ficha de una versión de otra empresa también da 404", f"HTTP {r.status_code}")

    # --- 6. Nota del doc de tareas: ¿desactivar la empresa corta el acceso? --
    print("\n=== 6. Company.is_active (nota de Friese_TAREAS_ClaudeCode.md) ===")
    guardar(sesion, f"/companies/company/{empresa.pk}/change/", {"is_active": ""})
    check(Company.objects.get(pk=empresa.pk).is_active is False,
          "la empresa queda desactivada desde el admin")
    fila = ultimo(Company, id=empresa.pk)
    check(fila.is_active is False and fila.history_user_id == superadmin.pk,
          "y la baja queda registrada en el historial con su autor")

    # Esto NO es un criterio de la 8.2: el doc de tareas pide aprovechar esta tarea
    # para CONFIRMAR qué hace hoy `is_active=False`. Se informa el resultado, no se
    # lo da por bueno ni por malo — la decisión es del usuario.
    r = requests.post(f"{API}/auth/login/",
                      json={"username": f"{TAG.lower()}_op", "password": pass_op}, timeout=30)
    login_ok = r.status_code == 200
    listado = requests.get(f"{API}/shipments/", timeout=30, headers=(
        {"Authorization": f"Bearer {r.json()['access']}"} if login_ok else {}))
    print(f"    login del operador: HTTP {r.status_code} | listado de remitos: "
          f"HTTP {listado.status_code}")
    if login_ok and listado.status_code == 200:
        print("    HALLAZGO: desactivar la empresa NO corta el acceso de sus usuarios.")
        print("      `Company.is_active` hoy no se consulta en ningún lado del backend")
        print("      (solo `User.is_active`). Para dar de baja a un cliente hay que")
        print("      desactivar sus usuarios uno por uno. Ver PROGRESS.md, tarea 8.2.")
    else:
        print("    desactivar la empresa SÍ corta el acceso.")

    # --- 7. El historial sobrevive al borrado del registro -----------------
    print("\n=== 7. Borrar el objeto no borra su historial ===")
    id_evidencia = evidencia.pk
    # Se relee de la base: la fila de baja copia el objeto que se borra, y el que
    # tenemos en memoria quedó viejo (le cambiamos el file_url desde el admin).
    Evidence.objects.get(pk=id_evidencia).delete()
    fila = ultimo(Evidence, id=id_evidencia)
    check(Evidence.history.filter(id=id_evidencia).count() >= 2,
          "el historial de la evidencia borrada sigue existiendo",
          Evidence.history.filter(id=id_evidencia).count())
    check(fila.history_type == "-", "con una última fila marcada como baja",
          fila.history_type)
    check(fila.file_url == "https://ejemplo.test/OTRA-foto.jpg",
          "y con los datos que tenía al momento de borrarse", fila.file_url)

    # --- 8. Visible en el panel, en el navegador --------------------------
    print("\n=== 8. Cómo se ve en el panel ===")
    nav = Browser(mobile=False)
    nav.send("Emulation.setDeviceMetricsOverride", {
        "width": 1440, "height": 900, "deviceScaleFactor": 1, "mobile": False})
    nav.goto(f"{ADMIN}/login/?next=/admin/")
    nav.wait("document.querySelector('#id_username')", label="form de login")
    nav.fill("#id_username", f"{TAG.lower()}_root")
    nav.fill("#id_password", pass_super)
    nav.js("document.querySelector('#login-form').submit()")
    nav.wait("document.querySelector('#user-tools')", label="entrada al panel")

    nav.goto(f"{ADMIN}/shipments/shipment/{remito.pk}/change/")
    check(bool(nav.js("!!document.querySelector('a.historylink')")),
          "la ficha del remito muestra el botón de historial")
    nav.goto(f"{ADMIN}/shipments/shipment/{remito.pk}/history/")
    nav.wait("document.querySelector('#change-history')", label="tabla del historial")
    tabla = nav.text("#change-history")
    check(f"{TAG.lower()}_root" in tabla, "en pantalla se lee el autor del cambio")
    # La columna "Qué cambió" muestra el verbose_name del campo, no su nombre
    # técnico: `receiver_name` se ve como "Receptor".
    check("Receptor" in tabla and f"Depósito {TAG}" in tabla,
          "y el campo que cambió, con su valor anterior")
    check("Modificación" in tabla and "Alta" in tabla,
          "el tipo de cambio se lee en castellano, como el resto del panel")
    nav.shot("h01-historial-remito")

    nav.goto(f"{ADMIN}{detalle}")
    nav.wait("document.querySelector('#content h1, #content-main')", label="ficha de la versión")
    check("Cómo estaba" in (nav.text("#content h1") or nav.js("document.title") or ""),
          "la ficha de una versión vieja se titula en castellano",
          nav.text("#content h1"))
    check(not nav.js("!!document.querySelector('.submit-row input[type=submit]')"),
          "y no tiene ningún botón que guarde o revierta")
    migas = nav.text(".breadcrumbs")
    check("Shipments" not in migas and "View" not in migas,
          "las migas de pan también quedan en castellano", migas.replace("\n", " "))
    nav.shot("h02-historial-version")

    lineas = "\n      ".join(l for l in tabla.splitlines() if l.strip())[:900]
    # La consola de Windows es cp1252 y la tabla trae flechas: se imprime tolerante.
    sys.stdout.buffer.write(("    filas en pantalla:\n      " + lineas + "\n").encode(
        sys.stdout.encoding or "utf-8", errors="replace"))
finally:
    # --- Limpieza: objetos Y su historial ---------------------------------
    ids_remitos = list(Shipment.objects.filter(
        company__in=empresas).values_list("id", flat=True))
    ids_usuarios = [u.pk for u in usuarios]
    ids_empresas = [c.pk for c in empresas]

    Evidence.objects.filter(shipment_id__in=ids_remitos).delete()
    ShipmentItem.objects.filter(shipment_id__in=ids_remitos).delete()
    Shipment.objects.filter(company__in=empresas).delete()
    Product.objects.filter(company__in=empresas).delete()
    User.objects.filter(pk__in=ids_usuarios).delete()
    Company.objects.filter(pk__in=ids_empresas).delete()

    # El historial NO se borra con su objeto (es el punto de la tarea): las filas
    # de esta corrida se limpian aparte, o la auditoría quedaría llena de remitos
    # y empresas que nunca existieron.
    borrar_historial(empresas=ids_empresas, usuarios=ids_usuarios, remitos=ids_remitos)

    if nav:
        nav.close()
    servidor.terminate()
    try:
        servidor.wait(timeout=10)
    except Exception:
        servidor.kill()

print(f"\n  limpieza: quedan {Shipment.history.count()} filas de historial de remitos, "
      f"{Company.history.count()} de empresas y {User.history.count()} de usuarios")
sys.exit(summary("historial de cambios (8.2)"))
