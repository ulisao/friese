"""Aviso por email a Friese cuando una empresa abre un ticket (tarea 9.2).

Sin esto, la 9.1 dejó un canal que solo se entera mirando el panel. Acá se
reusa la capa de emails de la Fase 5 (`shipments/emails.py`: el envío por
Resend, el envoltorio HTML y el armado del remitente) tal cual, con el mismo
criterio que `users/emails.py` en la 7.4 — mover esa capa a un módulo
compartido sería un refactor que nadie pidió y tocaría los cinco emails ya
verificados en producción.

Dos diferencias con los emails de producto:

- El destinatario es Friese (`SUPPORT_NOTIFICATION_EMAIL`), no la empresa ni el
  receptor, así que el envío NO se cuenta en el `UsageLog` de la empresa
  (`_deliver(payload, None)`): la empresa no consumió un email de su cupo, es
  Friese avisándose a sí misma. Mismo criterio que `ops/alerts.py` en la 7.1.
- El link del ticket apunta al Django Admin, que es donde vive el ticket (no hay
  pantalla de soporte en el frontend). La base del link sale del request que
  creó el ticket, igual que el link al panel de la 7.4: es el host por el que se
  está entrando de verdad y evita una variable de entorno más.

Regla de la capa, igual que en la 5.x: mandar el email NUNCA puede voltear una
operación ya commiteada. El ticket ya está guardado cuando esto corre (se llama
desde `transaction.on_commit`), así que no levanta excepciones — devuelve un
bool y deja la falla en el log.
"""

import logging

from django.conf import settings
from django.urls import reverse
from django.utils.html import escape

# Piezas compartidas de la capa de emails (tarea 5.1). Son privadas del módulo,
# pero se importan a propósito: es reuso, no una API nueva (mismo criterio que
# `users/emails.py`).
from shipments.emails import (
    _deliver,
    _format_datetime,
    _from_header,
    _html_document,
    _link_block_html,
)

logger = logging.getLogger(__name__)


def support_recipients():
    """Casillas de Friese que reciben el aviso de ticket nuevo.

    Separadas por coma, igual que `BACKUP_ALERT_EMAIL` (7.1): el aviso puede ir a
    más de una persona cuando soporte lo atienda alguien más.
    """
    return [
        address.strip()
        for address in settings.SUPPORT_NOTIFICATION_EMAIL.split(",")
        if address.strip()
    ]


def build_ticket_admin_link(ticket, request):
    """URL absoluta de la ficha del ticket en el Django Admin.

    `build_absolute_uri` toma el esquema y el host del request que creó el
    ticket —el mismo host por el que el admin de la empresa está entrando al
    panel, ya validado contra ALLOWED_HOSTS—, así que el link sale correcto en
    desarrollo y en producción sin una variable de entorno nueva.
    """
    path = reverse("admin:support_supportticket_change", args=[ticket.pk])
    return request.build_absolute_uri(path)


def _new_ticket_email_content(ticket, link):
    """Asunto + cuerpo (HTML y texto plano) del aviso de ticket nuevo."""
    company_name = ticket.company.name
    author = ticket.created_by.get_username()
    author_email = (ticket.created_by.email or "").strip()
    description = (ticket.description or "").strip()

    subject = f"Ticket #{ticket.pk} de {company_name} — {ticket.subject}"

    facts = [
        ("Empresa", company_name),
        ("Asunto", ticket.subject),
        ("Abierto por", f"{author} ({author_email})" if author_email else author),
        ("Fecha", _format_datetime(ticket.created_at)),
    ]

    text_facts = "\n".join(f"- {label}: {value}" for label, value in facts)
    text = (
        f"Hola,\n\n"
        f"{company_name} abrió el ticket de soporte #{ticket.pk}.\n\n"
        f"{text_facts}\n\n"
        f"Lo que escribieron:\n"
        f"{description}\n\n"
        f"Abrí el ticket en el panel para responderlo y moverle el estado:\n\n"
        f"{link}\n\n"
        f"--\n"
        f"Friese — trazabilidad de entregas con evidencia fotográfica"
    )

    html_facts = "".join(
        f"""\
      <tr>
        <td style="padding:2px 12px 2px 0;color:#71717a;white-space:nowrap;">{escape(label)}</td>
        <td style="padding:2px 0;">{escape(value)}</td>
      </tr>"""
        for label, value in facts
    )

    html = _html_document(
        f"""\
    <p style="margin:0 0 16px;">Hola,</p>
    <p style="margin:0 0 16px;">
      <strong>{escape(company_name)}</strong> abrió el ticket de soporte
      <strong>#{ticket.pk}</strong>.
    </p>
    <table style="margin:0 0 24px;font-size:14px;border-collapse:collapse;">
{html_facts}
    </table>
    <p style="margin:0 0 8px;font-size:14px;color:#71717a;">Lo que escribieron</p>
    <div style="margin:0 0 24px;padding:12px 16px;background-color:#f4f4f5;
                border-left:4px solid #4F46E5;border-radius:4px;
                white-space:pre-wrap;">{escape(description)}</div>
{_link_block_html(link, "Abrir el ticket en el panel")}""",
        # Este aviso va a la MISMA casilla que se ofrece como soporte (7.7): que
        # se invite a escribirle a uno mismo no tiene sentido.
        soporte=False,
    )

    return subject, html, text


def send_new_ticket_email(ticket, link):
    """Le avisa a Friese que se abrió un ticket. True solo si Resend lo aceptó.

    Lo dispara el alta del ticket en el admin (`support/admin.py`), después del
    commit. No levanta excepciones: el ticket ya está guardado y una falla de
    Resend no puede voltearlo — queda en el log.
    """
    recipients = support_recipients()
    if not recipients:
        logger.warning(
            "SUPPORT_NOTIFICATION_EMAIL vacía: el ticket #%s de la empresa %s no le "
            "avisa a nadie.",
            ticket.pk,
            ticket.company_id,
        )
        return False

    subject, html, text = _new_ticket_email_content(ticket, link)

    logger.info(
        "Ticket #%s abierto por %s: avisando a %s. Link: %s",
        ticket.pk,
        ticket.company_id,
        ", ".join(recipients),
        link,
    )
    payload = {
        # Lo manda Friese a Friese: el remitente va sin el nombre de la empresa
        # (a diferencia de los emails al receptor, donde la empresa emisora es la
        # que tiene que reconocerse).
        "from": _from_header(None),
        "to": recipients,
        "subject": subject,
        "html": html,
        "text": text,
    }
    # Responder el email es responderle a quien abrió el ticket, que es con quien
    # hay que resolver el pedido. El email del usuario es opcional en el alta
    # (tarea 4.4), así que puede no haber a quién.
    author_email = (ticket.created_by.email or "").strip()
    if author_email:
        payload["reply_to"] = [author_email]
    # `None`: el aviso va a Friese, no lo consume la empresa (ver el docstring).
    return _deliver(payload, None)
