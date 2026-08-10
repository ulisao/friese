"""Cierre automático de los remitos que vencieron sin respuesta (tarea 3.3).

Regla de la sección 6 de docs/desarrollo.md: pasadas las 48hs desde la primera
apertura del link (response_deadline), si el receptor no aceptó ni disputó, el
sistema cierra el remito como `accepted`.

Se corre como tarea periódica con django-crontab (CRONJOBS en config/settings.py)
y también a mano:

    python manage.py close_expired_shipments
"""

import logging

from django.core.management.base import BaseCommand
from django.utils import timezone

from shipments.models import Shipment

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = (
        "Cierra como 'accepted' los remitos en 'dispatched' cuya ventana de "
        "respuesta de 48hs venció sin respuesta del receptor."
    )

    def handle(self, *args, **options):
        now = timezone.now()

        # Candidatos: despachados, con la ventana ya sellada (response_deadline se
        # calcula en la primera apertura del link, tarea 3.1) y vencida. Un remito
        # cuyo link nunca se abrió tiene response_deadline null: su ventana no
        # empezó a correr, así que NO se cierra.
        candidates = Shipment.objects.filter(
            status=Shipment.DISPATCHED,
            response_deadline__isnull=False,
            response_deadline__lte=now,
        ).order_by("pk")

        closed_ids = []
        for shipment_id in candidates.values_list("pk", flat=True):
            # La condición status=dispatched viaja DENTRO del UPDATE, igual que en
            # la respuesta del receptor (views.close_response): si el receptor
            # acepta o disputa justo entre el SELECT y el UPDATE, acá se actualizan
            # 0 filas y su respuesta gana. update() y no save() a propósito: los
            # signals de Shipment son los del despacho (trial + UsageLog + email).
            # auto_closed marca que la conformidad es por silencio del receptor, no
            # expresa: es lo que después permite medir cuántos clientes no responden.
            updated = Shipment.objects.filter(
                pk=shipment_id, status=Shipment.DISPATCHED
            ).update(status=Shipment.ACCEPTED, auto_closed=True)
            if updated:
                closed_ids.append(shipment_id)

        if closed_ids:
            logger.info(
                "Cierre automático: %s remito(s) cerrado(s) como accepted por "
                "vencimiento de la ventana de respuesta: %s",
                len(closed_ids),
                ", ".join(f"#{pk}" for pk in closed_ids),
            )
            self.stdout.write(
                self.style.SUCCESS(
                    f"{len(closed_ids)} remito(s) cerrado(s) como accepted: "
                    + ", ".join(f"#{pk}" for pk in closed_ids)
                )
            )
        else:
            self.stdout.write("No hay remitos vencidos para cerrar.")
