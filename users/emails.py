"""Email de recuperación de contraseña (tarea 7.4).

La capa de emails del proyecto vive en `shipments/emails.py` desde la 5.1: ahí
están el envío por Resend, el envoltorio HTML y el armado del remitente. Acá se
reusan esas piezas tal cual en vez de duplicarlas o de mudarlas a un módulo
compartido: mover la capa sería un refactor que nadie pidió y tocaría los cuatro
emails ya verificados en producción.

Igual que el resto de la capa, `send_password_reset_email()` no levanta
excepciones: si Resend falla, queda en el log y devuelve False. El endpoint que
lo llama responde lo mismo en los dos casos (ver users/password_reset.py: la
respuesta es genérica a propósito, para no revelar si el usuario existe).
"""

import logging

from django.conf import settings
from django.utils.html import escape

# Piezas compartidas de la capa de emails (tarea 5.1). Son privadas del módulo,
# pero se importan a propósito: es reuso, no una API nueva.
from shipments.emails import (
    _deliver,
    _from_header,
    _html_document,
    _link_block_html,
)

logger = logging.getLogger(__name__)


def build_reset_link(uid, token):
    """URL de la pantalla del frontend donde se elige la contraseña nueva.

    Es la misma pantalla para el operador y para el admin de empresa: el link no
    depende del rol, solo del par uid + token que valida el backend.
    """
    base = settings.FRONTEND_PUBLIC_URL.rstrip("/")
    return f"{base}/restablecer/{uid}/{token}"


def _where_to_login_text(user, admin_url):
    """Dónde vuelve a entrar este usuario después de cambiar la contraseña.

    El operador entra a la app; el admin de empresa, al panel. El link del panel
    lo arma la vista con el host de la propia API (`request.build_absolute_uri`),
    así que no hace falta una variable de entorno nueva.
    """
    if user.is_staff and admin_url:
        return "el panel de administración", admin_url
    return "la app de Friese", settings.FRONTEND_PUBLIC_URL.rstrip("/")


def _reset_email_content(user, link, hours, admin_url):
    """Asunto + cuerpo (HTML y texto plano) del email de recuperación."""
    username = user.get_username()
    donde, donde_url = _where_to_login_text(user, admin_url)

    subject = "Recuperá tu contraseña de Friese"

    text = (
        f"Hola,\n\n"
        f"Pediste recuperar la contraseña de tu usuario de Friese.\n\n"
        f"Usuario: {username}\n\n"
        f"Abrí este link para elegir una contraseña nueva:\n\n"
        f"{link}\n\n"
        f"El link vence en {hours} horas y se puede usar UNA sola vez.\n\n"
        f"Cuando termines, entrá a {donde}: {donde_url}\n\n"
        f"Si no pediste esto, ignorá el email: tu contraseña sigue siendo la de "
        f"siempre.\n\n"
        f"--\n"
        f"Friese — trazabilidad de entregas con evidencia fotográfica"
    )

    html = _html_document(
        f"""\
    <p style="margin:0 0 16px;">Hola,</p>
    <p style="margin:0 0 16px;">
      Pediste recuperar la contraseña de tu usuario de Friese
      (<strong>{escape(username)}</strong>).
    </p>
    <p style="margin:0 0 24px;">Elegí una contraseña nueva:</p>
{_link_block_html(link, "Elegir contraseña nueva")}
    <p style="margin:0 0 16px;font-size:14px;color:#52525b;">
      El link vence en <strong>{hours} horas</strong> y se puede usar
      <strong>una sola vez</strong>.
    </p>
    <p style="margin:0 0 16px;font-size:14px;color:#52525b;">
      Cuando termines, entrá a {escape(donde)}:
      <a href="{escape(donde_url)}" style="color:#4F46E5;">{escape(donde_url)}</a>
    </p>
    <p style="margin:0 0 24px;font-size:14px;color:#52525b;">
      Si no pediste esto, ignorá el email: tu contraseña sigue siendo la de siempre.
    </p>"""
    )

    return subject, html, text


def send_password_reset_email(user, link, admin_url=None):
    """Le manda al usuario el link para elegir una contraseña nueva. True si salió.

    El remitente va sin el nombre de la empresa (`_from_header(None)`): este email
    lo manda Friese, no la empresa del usuario — a diferencia de los del receptor,
    donde la empresa emisora es la que tiene que reconocerse.
    """
    hours = settings.PASSWORD_RESET_TIMEOUT // 3600
    subject, html, text = _reset_email_content(user, link, hours, admin_url)

    logger.info(
        "Recuperación de contraseña: enviando el link al usuario %s.",
        user.get_username(),
    )
    payload = {
        "from": _from_header(None),
        "to": [user.email],
        "subject": subject,
        "html": html,
        "text": text,
    }
    return _deliver(payload, user.company_id)
