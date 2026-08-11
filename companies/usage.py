"""Contadores de uso por empresa y mes (docs/Desarrollo.md sección 6).

UsageLog se actualiza únicamente a través de `increment_usage()`: lo llaman el signal
de despacho y el de evidencia (shipments/signals.py) y el envío de emails
(shipments/emails.py). Así la regla de "un UsageLog por empresa y mes" y la suma
atómica en la DB tienen una sola implementación.
"""

from django.db.models import F
from django.utils import timezone

from .models import UsageLog


def increment_usage(company_id, field, moment=None):
    """Suma 1 al contador `field` del UsageLog de la empresa para el mes de `moment`.

    El mes es "YYYY-MM" en la TZ del proyecto. El F()+1 hace la suma en la DB, así que
    dos eventos concurrentes no se pisan.
    """
    month = timezone.localtime(moment or timezone.now()).strftime("%Y-%m")
    usage, _ = UsageLog.objects.get_or_create(company_id=company_id, month=month)
    UsageLog.objects.filter(pk=usage.pk).update(**{field: F(field) + 1})
