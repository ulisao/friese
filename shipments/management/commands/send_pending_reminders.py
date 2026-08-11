"""Recordatorio al receptor que no abrió el link del remito (tarea 5.2).

Sección 8 de docs/Desarrollo.md (Fase 5 — Notificaciones): "Recordatorio automático
si el link no fue abierto en X horas". El spec no define X; son
`settings.REMINDER_AFTER_HOURS` (24 por defecto, decisión de la tarea 5.2 confirmada
con el usuario), configurable por env.

Se corre como tarea periódica con django-crontab (CRONJOBS en config/settings.py)
y también a mano:

    python manage.py send_pending_reminders

El recordatorio sale UNA SOLA VEZ por remito: `Shipment.reminder_sent_at` se marca
antes de enviar y el propio filtro lo excluye en las corridas siguientes.
"""

import logging
from datetime import timedelta

from django.conf import settings
from django.core.management.base import BaseCommand
from django.utils import timezone

from shipments.emails import send_reminder_email
from shipments.models import Shipment

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = (
        "Envía el recordatorio al receptor de los remitos despachados hace más de "
        "REMINDER_AFTER_HOURS cuyo link todavía no fue abierto (una sola vez por remito)."
    )

    def handle(self, *args, **options):
        hours = settings.REMINDER_AFTER_HOURS
        now = timezone.now()
        cutoff = now - timedelta(hours=hours)

        # Candidatos: despachados hace más de `hours`, con el link nunca abierto
        # (link_opened_at lo sella la primera apertura, tarea 3.1) y sin recordatorio
        # previo. Los remitos sin receiver_email quedan afuera del filtro en vez de
        # marcarse como recordados: no se les mandó nada, así que si mañana se les
        # carga el email todavía pueden recibirlo.
        # Se materializa la lista ANTES de empezar a marcar: el UPDATE toca
        # reminder_sent_at, que es parte del propio filtro.
        candidates = list(
            Shipment.objects.filter(
                status=Shipment.DISPATCHED,
                link_opened_at__isnull=True,
                reminder_sent_at__isnull=True,
                dispatched_at__isnull=False,
                dispatched_at__lte=cutoff,
            )
            .exclude(receiver_email="")
            .select_related("company")
            .order_by("pk")
        )

        sent_ids = []
        failed_ids = []
        for shipment in candidates:
            # Se marca ANTES de enviar, y las condiciones viajan DENTRO del UPDATE
            # (mismo criterio que close_expired_shipments): si el receptor abre el
            # link o si dos corridas se pisan, acá se actualizan 0 filas y no sale un
            # segundo email. Es a lo sumo una vez: si Resend falla, el remito queda
            # marcado igual y no se reintenta (queda en el log).
            marked = Shipment.objects.filter(
                pk=shipment.pk,
                status=Shipment.DISPATCHED,
                link_opened_at__isnull=True,
                reminder_sent_at__isnull=True,
            ).update(reminder_sent_at=now)
            if not marked:
                continue

            shipment.reminder_sent_at = now
            if send_reminder_email(shipment):
                sent_ids.append(shipment.pk)
            else:
                failed_ids.append(shipment.pk)

        if sent_ids:
            logger.info(
                "Recordatorio enviado a %s remito(s) sin abrir: %s",
                len(sent_ids),
                ", ".join(f"#{pk}" for pk in sent_ids),
            )
            self.stdout.write(
                self.style.SUCCESS(
                    f"{len(sent_ids)} recordatorio(s) enviado(s): "
                    + ", ".join(f"#{pk}" for pk in sent_ids)
                )
            )
        if failed_ids:
            logger.warning(
                "El recordatorio NO pudo enviarse en %s remito(s) (quedan marcados, "
                "no se reintenta): %s",
                len(failed_ids),
                ", ".join(f"#{pk}" for pk in failed_ids),
            )
            self.stdout.write(
                self.style.WARNING(
                    f"{len(failed_ids)} recordatorio(s) fallaron: "
                    + ", ".join(f"#{pk}" for pk in failed_ids)
                )
            )
        if not sent_ids and not failed_ids:
            self.stdout.write("No hay remitos sin abrir para recordar.")
