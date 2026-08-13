"""Emails transaccionales de Friese, enviados con Resend por API HTTP.

docs/Desarrollo.md sección 1.1 (Emails: Resend) y sección 8 (Fase 5 —
Notificaciones). Tarea 5.1: el email al receptor con el link único del remito,
disparado por el despacho (shipments/signals.py). Tarea 5.2: el recordatorio al
receptor que no abrió el link, disparado por la tarea periódica
(shipments/management/commands/send_pending_reminders.py). Tarea 5.3: el aviso al
admin de la empresa cuando el receptor dispara una queja, disparado por el endpoint
público de dispute (shipments/views.py). Tarea 5.4: la confirmación al receptor del
remito que se cerró solo por silencio, disparada por la tarea periódica de cierre
(shipments/management/commands/close_expired_shipments.py).

Regla de la capa: enviar un email NUNCA puede voltear una operación ya commiteada.
`send_dispatch_email()` se llama desde `transaction.on_commit`, o sea que el remito
ya está despachado y no hay vuelta atrás; por eso no levanta excepciones, devuelve
un bool y deja la falla en el log.
"""

import logging
from email.utils import formataddr

import resend
from django.conf import settings
from django.contrib.auth import get_user_model
from django.utils import timezone
from django.utils.html import escape
from resend.http_client_requests import RequestsClient

from companies.usage import increment_usage

from .models import Evidence

logger = logging.getLogger(__name__)

# El envío corre dentro del request de despacho (on_commit), así que no puede colgarse:
# el default del SDK son 30s. Con 10s una caída de Resend demora el 200 del dispatch lo
# mínimo indispensable.
RESEND_TIMEOUT_SECONDS = 10
resend.default_http_client = RequestsClient(timeout=RESEND_TIMEOUT_SECONDS)


def build_public_link(shipment):
    """URL pública del remito para el receptor (usa el public_token del despacho)."""
    base = settings.FRONTEND_PUBLIC_URL.rstrip("/")
    return f"{base}/remito/{shipment.public_token}"


def _from_header(company_name):
    """Remitente del email: la dirección del env con el nombre de la empresa emisora.

    El receptor reconoce a la empresa que le despachó, no a Friese, así que el display
    name lleva su nombre. La dirección tiene que ser de un dominio verificado en Resend
    (ver RESEND_FROM_EMAIL en settings). `formataddr` se encarga de entrecomillar los
    nombres con comas o acentos.
    """
    address = settings.RESEND_FROM_EMAIL.strip()
    # Tolera que el env venga como "Nombre <casilla@dominio>": se usa solo la casilla.
    if "<" in address and ">" in address:
        address = address.split("<", 1)[1].split(">", 1)[0].strip()

    name = f"{company_name} vía Friese" if company_name else "Friese"
    return formataddr((name, address))


# --- Piezas compartidas por los emails al receptor -------------------------------
#
# Ningún doc define los textos; están redactados en castellano rioplatense, igual que
# el resto de la app, y las reglas que mencionan son las de la sección 6 (ventana de
# 48hs desde la PRIMERA APERTURA del link y cierre automático como aceptado).
#
# El HTML lleva los estilos inline: los clientes de email no soportan hojas de estilo
# ni clases. Fondo claro (el modo oscuro de docs/diseno.md es el de la app, no el del
# email) con el indigo funcional #4F46E5 en el botón.

_SIGNATURE = "Friese — trazabilidad de entregas con evidencia fotográfica"

_DEADLINE_TEXT = (
    "Tenés 48 horas desde que abrís el link para responder. Si no respondés en "
    "ese plazo, el remito se cierra automáticamente como aceptado."
)

_DEADLINE_HTML = """\
    <p style="margin:0 0 24px;font-size:14px;color:#52525b;">
      Tenés <strong>48 horas</strong> desde que abrís el link para responder. Si no
      respondés en ese plazo, el remito se cierra automáticamente como aceptado.
    </p>"""


def _greeting(shipment):
    receiver = (shipment.receiver_name or "").strip()
    return f"Hola {receiver}," if receiver else "Hola,"


def _format_datetime(moment):
    """Fecha y hora en la zona del proyecto, como se muestra en el resto de la app."""
    if moment is None:
        return "—"
    return timezone.localtime(moment).strftime("%d/%m/%Y %H:%M")


def _link_block_html(link, label):
    """Botón al remito + el link a la vista, para el que no puede clickear el botón."""
    return f"""\
    <p style="margin:0 0 24px;text-align:center;">
      <a href="{escape(link)}"
         style="display:inline-block;padding:14px 28px;background-color:#4F46E5;
                color:#ffffff;text-decoration:none;border-radius:6px;font-weight:600;">
        {escape(label)}
      </a>
    </p>
    <p style="margin:0 0 24px;font-size:14px;color:#52525b;">
      Si el botón no funciona, copiá y pegá este link en tu navegador:<br>
      <a href="{escape(link)}" style="color:#4F46E5;">{escape(link)}</a>
    </p>"""


def _html_document(body):
    """Envuelve el cuerpo en la caja y el pie que comparten todos los emails."""
    return f"""\
<div style="margin:0;padding:24px 12px;background-color:#f4f4f5;">
  <div style="max-width:520px;margin:0 auto;padding:32px 24px;background-color:#ffffff;
              border-radius:8px;font-family:Helvetica,Arial,sans-serif;font-size:16px;
              line-height:1.5;color:#27272a;">
{body}
    <p style="margin:0;padding-top:16px;border-top:1px solid #e4e4e7;font-size:13px;
              color:#71717a;">
      {_SIGNATURE}
    </p>
  </div>
</div>"""


def _dispatch_email_content(shipment, link):
    """Asunto + cuerpo (HTML y texto plano) del email de despacho (tarea 5.1)."""
    company_name = shipment.company.name
    greeting = _greeting(shipment)

    subject = f"Remito #{shipment.pk} de {company_name} — confirmá la recepción"

    text = (
        f"{greeting}\n\n"
        f"{company_name} despachó el remito #{shipment.pk} y necesita que confirmes "
        f"la recepción.\n\n"
        f"Abrí este link para ver los productos y las fotos del despacho, y dejar tu "
        f"conformidad o reportar un problema:\n\n"
        f"{link}\n\n"
        f"{_DEADLINE_TEXT}\n\n"
        f"--\n"
        f"{_SIGNATURE}"
    )

    html = _html_document(
        f"""\
    <p style="margin:0 0 16px;">{escape(greeting)}</p>
    <p style="margin:0 0 16px;">
      <strong>{escape(company_name)}</strong> despachó el remito
      <strong>#{shipment.pk}</strong> y necesita que confirmes la recepción.
    </p>
    <p style="margin:0 0 24px;">
      Abrí el remito para ver los productos y las fotos del despacho, y dejar tu
      conformidad o reportar un problema:
    </p>
{_link_block_html(link, "Ver el remito")}
{_DEADLINE_HTML}"""
    )

    return subject, html, text


def _reminder_email_content(shipment, link, hours):
    """Asunto + cuerpo del recordatorio para el receptor que no abrió el link (5.2)."""
    company_name = shipment.company.name
    greeting = _greeting(shipment)

    subject = f"Recordatorio: el remito #{shipment.pk} de {company_name} sigue sin abrir"

    text = (
        f"{greeting}\n\n"
        f"Hace más de {hours} horas que {company_name} despachó el remito "
        f"#{shipment.pk} y todavía no abriste el link para confirmar la recepción.\n\n"
        f"Abrilo para ver los productos y las fotos del despacho, y dejar tu "
        f"conformidad o reportar un problema:\n\n"
        f"{link}\n\n"
        f"{_DEADLINE_TEXT}\n\n"
        f"--\n"
        f"{_SIGNATURE}"
    )

    html = _html_document(
        f"""\
    <p style="margin:0 0 16px;">{escape(greeting)}</p>
    <p style="margin:0 0 16px;">
      Hace más de <strong>{hours} horas</strong> que
      <strong>{escape(company_name)}</strong> despachó el remito
      <strong>#{shipment.pk}</strong> y todavía no abriste el link para confirmar
      la recepción.
    </p>
    <p style="margin:0 0 24px;">
      Abrilo para ver los productos y las fotos del despacho, y dejar tu conformidad
      o reportar un problema:
    </p>
{_link_block_html(link, "Ver el remito")}
{_DEADLINE_HTML}"""
    )

    return subject, html, text


def _auto_close_email_content(shipment, link):
    """Asunto + cuerpo de la confirmación de cierre automático al receptor (5.4).

    Es el único email al receptor que NO lleva el aviso de las 48hs: acá la ventana
    ya venció, que es justamente el motivo del email.
    """
    company_name = shipment.company.name
    greeting = _greeting(shipment)
    deadline = _format_datetime(shipment.response_deadline)

    subject = f"Remito #{shipment.pk} de {company_name} — cerrado como aceptado"

    text = (
        f"{greeting}\n\n"
        f"El plazo de 48 horas para responder el remito #{shipment.pk} de "
        f"{company_name} venció el {deadline} sin que registráramos tu respuesta, "
        f"así que el remito quedó cerrado automáticamente como ACEPTADO.\n\n"
        f"Podés seguir viendo el remito, con los productos y las fotos del despacho, "
        f"en este link:\n\n"
        f"{link}\n\n"
        f"Si hubo algún problema con la entrega, comunicate directamente con "
        f"{company_name}.\n\n"
        f"--\n"
        f"{_SIGNATURE}"
    )

    html = _html_document(
        f"""\
    <p style="margin:0 0 16px;">{escape(greeting)}</p>
    <p style="margin:0 0 16px;">
      El plazo de 48 horas para responder el remito <strong>#{shipment.pk}</strong> de
      <strong>{escape(company_name)}</strong> venció el {escape(deadline)} sin que
      registráramos tu respuesta, así que el remito quedó cerrado automáticamente como
      <strong>aceptado</strong>.
    </p>
    <p style="margin:0 0 24px;">
      Podés seguir viendo el remito, con los productos y las fotos del despacho:
    </p>
{_link_block_html(link, "Ver el remito")}
    <p style="margin:0 0 24px;font-size:14px;color:#52525b;">
      Si hubo algún problema con la entrega, comunicate directamente con
      {escape(company_name)}.
    </p>"""
    )

    return subject, html, text


def _dispute_email_content(shipment, photos, reported_at):
    """Asunto + cuerpo del aviso de queja al admin de la empresa (tarea 5.3).

    A diferencia de los dos emails al receptor, este va hacia adentro de la empresa:
    lo importante es el detalle de la queja (quién, cuándo, por qué y con qué fotos),
    no el link del remito.
    """
    company_name = shipment.company.name
    receiver = (shipment.receiver_name or "").strip() or "El receptor"
    reason = (shipment.dispute_reason or "").strip()
    no_reason = "El receptor no dejó un motivo escrito."

    subject = f"Queja en el remito #{shipment.pk} — {receiver}"

    facts = [
        ("Remito", f"#{shipment.pk}"),
        (
            "Receptor",
            f"{receiver} ({shipment.receiver_email})"
            if shipment.receiver_email
            else receiver,
        ),
        ("Despachado por", shipment.operator.get_username()),
        ("Fecha de despacho", _format_datetime(shipment.dispatched_at)),
        ("Queja recibida", _format_datetime(reported_at)),
        ("Fotos de la recepción", str(len(photos))),
    ]

    text_facts = "\n".join(f"- {label}: {value}" for label, value in facts)
    text_photos = (
        "\n".join(photo.file_url for photo in photos)
        if photos
        else "El receptor no adjuntó fotos."
    )
    text = (
        f"Hola,\n\n"
        f"{receiver} reportó un problema con el remito #{shipment.pk} de "
        f"{company_name}.\n\n"
        f"Motivo de la queja:\n"
        f"{reason or no_reason}\n\n"
        f"Datos del remito:\n"
        f"{text_facts}\n\n"
        f"Fotos de la carga recibida:\n"
        f"{text_photos}\n\n"
        f"--\n"
        f"{_SIGNATURE}"
    )

    html_facts = "".join(
        f"""\
      <tr>
        <td style="padding:2px 12px 2px 0;color:#71717a;white-space:nowrap;">{escape(label)}</td>
        <td style="padding:2px 0;">{escape(value)}</td>
      </tr>"""
        for label, value in facts
    )
    # Las fotos van como miniatura clickeable. Si el cliente de email bloquea las
    # imágenes remotas (lo habitual por defecto), queda el texto alternativo con el
    # link, que abre la foto en R2 igual.
    html_photos = (
        "".join(
            f"""\
      <a href="{escape(photo.file_url)}" style="display:inline-block;margin:0 8px 8px 0;">
        <img src="{escape(photo.file_url)}" width="180"
             alt="Foto {index} de la carga recibida"
             style="width:180px;max-width:100%;border-radius:6px;border:1px solid #e4e4e7;">
      </a>"""
            for index, photo in enumerate(photos, start=1)
        )
        if photos
        else """\
      <p style="margin:0;font-size:14px;color:#52525b;">El receptor no adjuntó fotos.</p>"""
    )

    html = _html_document(
        f"""\
    <p style="margin:0 0 16px;">Hola,</p>
    <p style="margin:0 0 16px;">
      <strong>{escape(receiver)}</strong> reportó un problema con el remito
      <strong>#{shipment.pk}</strong> de <strong>{escape(company_name)}</strong>.
    </p>
    <p style="margin:0 0 8px;font-size:14px;color:#71717a;">Motivo de la queja</p>
    <div style="margin:0 0 24px;padding:12px 16px;background-color:#fef2f2;
                border-left:4px solid #ef4444;border-radius:4px;white-space:pre-wrap;">{escape(reason) or f'<em style="color:#52525b;">{no_reason}</em>'}</div>
    <table style="margin:0 0 24px;font-size:14px;border-collapse:collapse;">
{html_facts}
    </table>
    <p style="margin:0 0 12px;font-size:14px;color:#71717a;">Fotos de la carga recibida</p>
    <div style="margin:0 0 24px;">
{html_photos}
    </div>"""
    )

    return subject, html, text


def _deliver(payload, company_id):
    """Manda el email por Resend y cuenta el envío en el UsageLog del mes.

    Devuelve True solo si Resend aceptó el email. No levanta nunca: cualquier falla
    (API key ausente, red caída, dominio sin verificar, rate limit) queda en el log.
    """
    if not settings.RESEND_API_KEY:
        logger.warning(
            "RESEND_API_KEY vacía: no se envía el email a %s (asunto: %s).",
            payload.get("to"),
            payload.get("subject"),
        )
        return False

    resend.api_key = settings.RESEND_API_KEY
    try:
        sent = resend.Emails.send(payload)
    except Exception:  # noqa: BLE001 — cualquier falla de Resend se traga a propósito
        logger.exception(
            "Resend no pudo enviar el email a %s (asunto: %s).",
            payload.get("to"),
            payload.get("subject"),
        )
        return False

    logger.info(
        "Email enviado por Resend a %s (id=%s).", payload.get("to"), sent.get("id")
    )
    # emails_sent del mes (sección 6). Se cuenta solo lo que Resend aceptó.
    # `company_id` puede venir en None desde la recuperación de contraseña (7.4):
    # el superadmin de Friese no pertenece a ninguna empresa y no hay UsageLog que
    # tocar. El resto de los emails siempre tiene empresa.
    if company_id:
        increment_usage(company_id, "emails_sent")
    return True


def _receiver_payload(shipment, subject, html, text):
    """Payload de Resend para un email dirigido al receptor del remito."""
    payload = {
        "from": _from_header(shipment.company.name),
        "to": [shipment.receiver_email],
        "subject": subject,
        "html": html,
        "text": text,
    }
    # El receptor contesta las dudas a la empresa que despachó, no a Friese.
    if shipment.company.email:
        payload["reply_to"] = [shipment.company.email]
    return payload


def send_dispatch_email(shipment):
    """Envía al receptor el link del remito recién despachado. True si se envió.

    receiver_email es opcional en el modelo (sección 3), así que un remito sin email
    se despacha igual: solo se deja constancia en el log y no se envía nada.
    """
    if not shipment.receiver_email:
        logger.warning(
            "Remito #%s despachado sin receiver_email: no se envía el link al receptor.",
            shipment.pk,
        )
        return False

    link = build_public_link(shipment)
    subject, html, text = _dispatch_email_content(shipment, link)

    logger.info(
        "Remito #%s despachado: enviando el link a %s. Link: %s",
        shipment.pk,
        shipment.receiver_email,
        link,
    )
    return _deliver(
        _receiver_payload(shipment, subject, html, text), shipment.company_id
    )


def send_reminder_email(shipment):
    """Le recuerda al receptor un remito cuyo link nunca abrió. True si se envió.

    Lo dispara la tarea periódica `send_pending_reminders` (tarea 5.2) pasadas
    REMINDER_AFTER_HOURS desde el despacho. Igual que el resto de la capa, no levanta
    excepciones: una falla de Resend queda en el log y devuelve False.
    """
    if not shipment.receiver_email:
        logger.warning(
            "Remito #%s sin receiver_email: no se envía el recordatorio.", shipment.pk
        )
        return False

    link = build_public_link(shipment)
    subject, html, text = _reminder_email_content(
        shipment, link, settings.REMINDER_AFTER_HOURS
    )

    logger.info(
        "Remito #%s sin abrir: enviando el recordatorio a %s. Link: %s",
        shipment.pk,
        shipment.receiver_email,
        link,
    )
    return _deliver(
        _receiver_payload(shipment, subject, html, text), shipment.company_id
    )


def send_auto_close_email(shipment):
    """Le confirma al receptor que el remito se cerró solo por silencio (5.4).

    Lo dispara la tarea periódica `close_expired_shipments` (tarea 3.3) después de
    cerrar el remito. Igual que el resto de la capa, no levanta excepciones: el
    remito ya está cerrado y una falla de Resend no puede voltearlo.
    """
    if not shipment.receiver_email:
        logger.warning(
            "Remito #%s cerrado automáticamente sin receiver_email: no se envía la "
            "confirmación de cierre.",
            shipment.pk,
        )
        return False

    link = build_public_link(shipment)
    subject, html, text = _auto_close_email_content(shipment, link)

    logger.info(
        "Remito #%s cerrado automáticamente: enviando la confirmación a %s.",
        shipment.pk,
        shipment.receiver_email,
    )
    return _deliver(
        _receiver_payload(shipment, subject, html, text), shipment.company_id
    )


def admin_recipients(company):
    """Casillas que reciben los avisos internos de la empresa (hoy, la queja).

    Una empresa puede tener más de un admin —Friese crea el primero con el alta
    (tarea 4.4) y él da de alta a los demás—, así que se les avisa a TODOS los que
    estén activos y tengan email cargado. El email del admin es opcional en el alta,
    así que si ninguno tiene uno el aviso va a la casilla de contacto de la empresa
    (`Company.email`, que sí es obligatoria) antes que perderse.
    """
    User = get_user_model()
    emails = (
        User.objects.filter(company=company, role=User.ADMIN, is_active=True)
        .exclude(email="")
        .order_by("pk")
        .values_list("email", flat=True)
    )
    # dict.fromkeys: dos admins pueden compartir casilla y Resend recibiría el duplicado.
    unique_emails = list(dict.fromkeys(emails))
    if unique_emails:
        return unique_emails
    if company.email:
        return [company.email]
    return []


def send_dispute_email(shipment):
    """Le avisa al admin de la empresa que el receptor disputó el remito (5.3).

    Lo dispara el endpoint público de dispute (shipments/views.py) después del
    commit de la queja. Igual que el resto de la capa, no levanta excepciones: la
    queja ya está registrada y una falla de Resend no puede voltearla.
    """
    recipients = admin_recipients(shipment.company)
    if not recipients:
        logger.warning(
            "Remito #%s disputado: la empresa %s no tiene ninguna casilla donde "
            "avisar la queja.",
            shipment.pk,
            shipment.company_id,
        )
        return False

    photos = list(
        shipment.evidence.filter(type=Evidence.RECEPTION).order_by("uploaded_at")
    )
    subject, html, text = _dispute_email_content(shipment, photos, timezone.now())

    logger.info(
        "Remito #%s disputado: avisando a %s.", shipment.pk, ", ".join(recipients)
    )
    payload = {
        # Este email va hacia adentro de la empresa: lo manda Friese, no la empresa
        # a su propio admin (por eso el remitente no lleva el nombre de la empresa).
        "from": _from_header(None),
        "to": recipients,
        "subject": subject,
        "html": html,
        "text": text,
    }
    # El admin le responde al receptor que se quejó, que es con quien tiene que
    # resolver el problema.
    if shipment.receiver_email:
        payload["reply_to"] = [shipment.receiver_email]
    return _deliver(payload, shipment.company_id)
