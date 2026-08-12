"""Avisos de infraestructura por email (tarea 7.1).

Separado de `shipments/emails.py` a propósito: aquellos son emails de producto —van a
un receptor o al admin de UNA empresa, y cuentan contra el `UsageLog` de esa empresa—.
Este va al que opera Friese y no pertenece a ninguna empresa, así que no se cuenta.

El criterio de aceptación de la tarea es que exista un backup de menos de 24hs *en
todo momento*. Un cron que falla en silencio rompe eso sin que nadie se entere hasta
el día que hay que restaurar, así que la falla se avisa.

Regla igual que en el resto del proyecto: mandar el email nunca puede empeorar las
cosas. No levanta excepciones — si Resend está caído, la falla del backup ya quedó en
el log y en el exit code del comando.
"""

import logging

import resend
from django.conf import settings
from resend.http_client_requests import RequestsClient

logger = logging.getLogger(__name__)

RESEND_TIMEOUT_SECONDS = 10
resend.default_http_client = RequestsClient(timeout=RESEND_TIMEOUT_SECONDS)


def alert_recipients():
    """Casillas que reciben los avisos de infraestructura."""
    return [
        address.strip()
        for address in settings.BACKUP_ALERT_EMAIL.split(",")
        if address.strip()
    ]


def send_ops_alert(subject, body):
    """Manda un aviso de infraestructura. True solo si Resend lo aceptó."""
    recipients = alert_recipients()
    if not recipients:
        logger.warning(
            "BACKUP_ALERT_EMAIL vacía: el aviso de infraestructura no se envía a "
            "nadie (asunto: %s).",
            subject,
        )
        return False
    if not settings.RESEND_API_KEY:
        logger.warning(
            "RESEND_API_KEY vacía: no se envía el aviso de infraestructura (asunto: %s).",
            subject,
        )
        return False

    resend.api_key = settings.RESEND_API_KEY
    try:
        sent = resend.Emails.send(
            {
                "from": settings.RESEND_FROM_EMAIL,
                "to": recipients,
                "subject": subject,
                # Solo texto: es un aviso operativo que se lee desde el celular, no
                # una pieza de producto. Sin HTML no hay nada que se rompa.
                "text": body,
            }
        )
    except Exception:  # noqa: BLE001 — una falla de Resend no puede tapar la del backup
        logger.exception(
            "Resend no pudo enviar el aviso de infraestructura a %s (asunto: %s).",
            ", ".join(recipients),
            subject,
        )
        return False

    logger.info(
        "Aviso de infraestructura enviado a %s (id=%s).",
        ", ".join(recipients),
        sent.get("id"),
    )
    return True
