"""Link y QR de la invitación de operador (docs/desarrollo.md sección 3).

El spec dice que "el QR que escanea el operador contiene la URL con este token".
Acá se arma esa URL y su QR, en un solo lugar, para que el admin de la empresa
pueda mostrárselo al operador sin salir del panel.
"""

import io

import qrcode
import qrcode.image.svg
from django.conf import settings

# Ruta de la pantalla de alta en el frontend. Vive acá y no desperdigada: si
# cambia, cambia en un solo lado (igual que `build_public_link` con el remito).
REGISTER_PATH = "alta-operador"


def build_invite_url(token):
    """URL que codifica el QR: la pantalla de alta con el token de la invitación."""
    base = settings.FRONTEND_PUBLIC_URL.rstrip("/")
    return f"{base}/{REGISTER_PATH}/{token}"


def build_invite_qr_svg(token):
    """El QR de esa URL, como SVG listo para embeber en el admin.

    SVG y no PNG a propósito: el factory de SVG de `qrcode` usa solo la stdlib,
    así que no hace falta Pillow (que el proyecto no tiene, y que además obligaría
    a sumar una dependencia binaria por un cuadradito en blanco y negro).
    """
    imagen = qrcode.make(
        build_invite_url(token),
        image_factory=qrcode.image.svg.SvgPathImage,
        box_size=10,
        border=2,
    )
    buffer = io.BytesIO()
    imagen.save(buffer)
    svg = buffer.getvalue().decode()
    # Se saca la declaración XML: adentro de una página HTML no va, y algunos
    # navegadores se quejan si aparece en el medio del documento.
    return svg.split("?>", 1)[-1].strip()
