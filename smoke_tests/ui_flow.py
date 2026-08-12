"""Fase 6.6 — el flujo completo por el NAVEGADOR, contra las URLs de producción.

Recorre lo mismo que `e2e.py` pero como lo hace una persona: la app de Vercel
(https://app.friese.com.ar) pegándole al backend de Railway. Cubre lo que la API
sola no prueba: que el build de producción trae la URL correcta de la API, que el
CORS deja pasar al navegador, que el ruteo del SPA resuelve el link del receptor y
que la cámara en vivo funciona sobre HTTPS.
"""

import json
import os
import sys

import django

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE_DIR)
sys.path.insert(0, HERE)
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
django.setup()

from shipments.models import Evidence, Shipment  # noqa: E402

from browser import Browser  # noqa: E402
from e2e import FRONTEND, check, summary  # noqa: E402

with open(os.path.join(HERE, "state.json"), encoding="utf-8") as fh:
    state = json.load(fh)

# El link de la card de un remito: /remitos/{id}, no /remitos/nuevo.
CARD_LINK = ("[...document.querySelectorAll('a[href^=\"/remitos/\"]')]"
             ".find(a => /\\/remitos\\/\\d+$/.test(a.getAttribute('href')))")

b = Browser()
try:
    # --- 1. Login del operador -------------------------------------------
    b.goto(f"{FRONTEND}/login")
    b.wait("document.querySelector('#username')", label="pantalla de login")
    b.shot("01-login")
    check(True, "la app de producción carga la pantalla de login")

    b.fill("#username", state["operator_username"])
    b.fill("#password", state["operator_password"])
    b.click("button[type=submit]")
    b.wait("location.pathname === '/'", label="entrar a la lista")
    # Se espera por la card de UN REMITO, no por cualquier `a[href^="/remitos/"]`:
    # el botón "Nuevo remito" es también un link con ese prefijo y ya está en pantalla
    # mientras la lista todavía dice "Cargando…".
    b.wait(CARD_LINK, label="lista cargada")
    b.shot("02-lista")
    check(True, "el operador entra con usuario y contraseña contra el backend de producción")

    lista = b.js("document.body.innerText")
    check("Acopio San Lorenzo" in lista and "Depósito Ruta 9" in lista,
          "la lista muestra los remitos de la empresa")
    check("Conforme" in lista or "Aceptado" in lista or "aceptado" in lista.lower(),
          "los estados se ven en la lista")

    # --- 2. Alta de remito -----------------------------------------------
    b.click("a[href='/remitos/nuevo']")
    b.wait("location.pathname === '/remitos/nuevo'", label="alta de remito")
    b.wait("document.querySelector('#product-search')", label="catálogo cargado")
    check(True, "el catálogo de productos carga desde el backend de producción")

    b.fill("#receiver-name", "Acopio Timbúes (SMOKE66 navegador)")
    b.fill("#receiver-email", "ulisessbaretta+smoke66@gmail.com")
    b.fill("#receiver-phone", "+54 9 341 555-0188")
    b.click("button[data-product-id]")
    b.wait("document.querySelector('#item-quantity')", label="cantidad del producto")
    b.fill("#item-quantity", "25")
    b.fill("#item-notes", "Pallet completo, film nuevo.")
    b.shot("03-alta-remito")
    b.js("""[...document.querySelectorAll('button')]
            .find(x => x.innerText.trim() === 'Agregar producto').click()""")
    b.wait("document.querySelector('[data-testid=shipment-items]')", label="ítem agregado")
    check(True, "se agrega un producto con cantidad y unidad")

    b.click("button[type=submit]")
    # Guardado el borrador la app vuelve a la lista; el remito nuevo es el primero
    # (el listado viene ordenado por -created_at).
    b.wait("location.pathname === '/'", timeout=60, label="vuelta a la lista")
    b.click_js(CARD_LINK, label="card del remito recién creado")
    b.wait("/^\\/remitos\\/\\d+$/.test(location.pathname)", label="detalle del remito nuevo")
    b.wait("document.querySelector('[data-testid=open-camera]')", label="detalle operable")
    shipment_id = int(b.js("location.pathname.split('/').pop()"))
    check(Shipment.objects.filter(pk=shipment_id, status=Shipment.DRAFT).exists(),
          f"el remito #{shipment_id} quedó guardado como borrador")
    b.shot("04-detalle-draft")

    # --- 3. Foto con la cámara en vivo -----------------------------------
    b.click("[data-testid=open-camera]")
    b.wait("document.querySelector('[data-testid=camera]')", label="visor de cámara")
    b.wait("document.querySelector('video') && document.querySelector('video').videoWidth > 0",
           label="stream de la cámara")
    b.shot("05-camara")
    check(True, "la cámara en vivo abre sobre HTTPS en producción")

    b.click("[data-testid=camera-shutter]")
    # La miniatura aparece enseguida, pero es la PREVIEW local mientras sube. Hay que
    # esperar a la foto ya confirmada por el backend: la que apunta a R2.
    b.wait("document.querySelector('[data-testid=evidence-list] img[src^=\"https://pub-\"]')",
           timeout=120, label="foto confirmada por el backend")
    check(Evidence.objects.filter(shipment_id=shipment_id).count() >= 1,
          "la foto sacada con la cámara quedó guardada en R2")
    b.shot("06-foto-subida")

    # --- 4. Despacho con confirmación ------------------------------------
    # Despachar queda deshabilitado mientras haya fotos subiendo (es a propósito).
    b.wait("!document.querySelector('[data-testid=dispatch]').disabled",
           timeout=120, label="el botón Despachar se habilita")
    b.click("[data-testid=dispatch]")
    b.wait("document.querySelector('[data-testid=dispatch-dialog]')", label="diálogo de despacho")
    b.shot("07-dialogo-despacho")
    check(Shipment.objects.get(pk=shipment_id).status == Shipment.DRAFT,
          "abrir el diálogo NO despacha: hace falta confirmar")

    b.click("[data-testid=dispatch-confirm]")
    b.wait("!document.querySelector('[data-testid=dispatch-dialog]')", timeout=90,
           label="despacho confirmado")
    b.wait("!document.querySelector('[data-testid=dispatch]')", timeout=60,
           label="el remito deja de ser operable")
    sh = Shipment.objects.get(pk=shipment_id)
    check(sh.status == Shipment.DISPATCHED and sh.public_token,
          "el remito quedó despachado con su public_token", str(sh.public_token))
    b.shot("08-detalle-despachado")
    check("Despachado" in b.js("document.body.innerText"),
          "el detalle pasa a modo lectura con el estado despachado")

    # --- 5. El receptor abre el link único y da conformidad --------------
    b.goto(f"{FRONTEND}/remito/{sh.public_token}")
    b.wait("document.querySelector('[data-testid=accept]')", label="pantalla del receptor")
    b.shot("09-receptor")
    check(True, "el link del receptor abre en producción sin login (ruteo del SPA)")
    receptor = b.js("document.body.innerText")
    check("Acopio Timbúes" in receptor and "25" in receptor,
          "el receptor ve el remito con su carga")
    check(b.js("!!document.querySelector('[data-testid=dispatch-evidence] img')"),
          "el receptor ve la foto de despacho servida desde R2")

    b.click("[data-testid=accept]")
    b.wait("document.querySelector('[data-testid=accept-dialog]')", label="diálogo de conformidad")
    b.shot("10-dialogo-conformidad")
    b.click("[data-testid=accept-confirm]")
    b.wait("document.querySelector('[data-testid=final-message]')", timeout=90,
           label="mensaje final")
    b.shot("11-receptor-conforme")
    check(Shipment.objects.get(pk=shipment_id).status == Shipment.ACCEPTED,
          "la conformidad del receptor quedó registrada")
    check(not b.js("!!document.querySelector('[data-testid=accept]')"),
          "respondido el remito, los botones desaparecen")

    # --- 6. Link inexistente ---------------------------------------------
    b.goto(f"{FRONTEND}/remito/00000000-0000-0000-0000-000000000000")
    b.wait("document.querySelector('[data-testid=load-error]')", label="error de link inválido")
    b.shot("12-link-invalido")
    err = b.text("[data-testid=load-error]")
    check(bool(err) and "404" not in err and "Error" not in err,
          "un link inexistente muestra un mensaje comprensible", err[:80])

    state["ui_shipment_id"] = shipment_id
    with open(os.path.join(HERE, "state.json"), "w", encoding="utf-8") as fh:
        json.dump(state, fh, indent=2, ensure_ascii=False)
finally:
    b.close()

sys.exit(summary("navegador"))
