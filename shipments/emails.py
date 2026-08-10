"""Email al receptor con el link del remito despachado.

STUB de la tarea 2.3: la integración real con Resend es la Fase 5 del roadmap
(docs/desarrollo.md sección 8, "Notificaciones"), que todavía no está hecha. Acá
solo se loguea el email que se enviaría, para no bloquear el flujo de despacho.
Cuando se implemente Fase 5, reemplazar el cuerpo de send_dispatch_email() por la
llamada a Resend: el resto del sistema no necesita cambiar.
"""

import logging

from django.conf import settings

logger = logging.getLogger(__name__)


def build_public_link(shipment):
    """URL pública del remito para el receptor (usa el public_token del despacho)."""
    base = settings.FRONTEND_PUBLIC_URL.rstrip("/")
    return f"{base}/remito/{shipment.public_token}"


def send_dispatch_email(shipment):
    """Envía al receptor el link del remito. Devuelve True si se envió.

    receiver_email es opcional en el modelo (sección 3), así que un remito sin email
    se despacha igual: solo se deja constancia en el log y no se envía nada.
    """
    if not shipment.receiver_email:
        logger.warning(
            "Remito #%s despachado sin receiver_email: no se envía el link al receptor.",
            shipment.pk,
        )
        return False

    logger.info(
        "[STUB email — Fase 5] Remito #%s despachado. Para: %s. Link: %s",
        shipment.pk,
        shipment.receiver_email,
        build_public_link(shipment),
    )
    return True
