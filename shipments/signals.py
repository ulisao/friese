"""Efectos automáticos sobre trial y UsageLog (docs/desarrollo.md sección 6).

Cada vez que un Shipment pasa a estado dispatched:
- se decrementa Company.trial_shipments_remaining en 1 (nunca por debajo de 0);
- se incrementa UsageLog.shipments_created del mes correspondiente;
- se dispara el email con el link al receptor (y ese envío suma UsageLog.emails_sent,
  ver shipments/emails.py).

Cada vez que se sube una foto de evidencia:
- se incrementa UsageLog.photos_uploaded del mes correspondiente.

El spec exige que UsageLog y el trial se actualicen vía signals, nunca a mano.
"""

from django.db import transaction
from django.db.models import F
from django.db.models.signals import post_save, pre_save
from django.dispatch import receiver

from companies.models import Company
from companies.usage import increment_usage

from .emails import send_dispatch_email
from .models import Evidence, Shipment

# Atributo temporal donde pre_save deja el status que el remito tenía en la DB.
_PREVIOUS_STATUS_ATTR = "_previous_status"


@receiver(pre_save, sender=Shipment)
def remember_previous_status(sender, instance, **kwargs):
    """Guarda el status previo para que post_save detecte la transición a dispatched."""
    if instance.pk is None:
        previous = None
    else:
        previous = (
            Shipment.objects.filter(pk=instance.pk)
            .values_list("status", flat=True)
            .first()
        )
    setattr(instance, _PREVIOUS_STATUS_ATTR, previous)


@receiver(post_save, sender=Shipment)
def on_shipment_dispatched(sender, instance, created, **kwargs):
    previous = getattr(instance, _PREVIOUS_STATUS_ATTR, None)
    # Solo la TRANSICIÓN hacia dispatched consume trial/UsageLog: si el remito ya
    # estaba dispatched y se vuelve a guardar, no se descuenta ni se cuenta de nuevo.
    if instance.status != Shipment.DISPATCHED or previous == Shipment.DISPATCHED:
        return

    # Trial: -1 y nunca por debajo de 0. El filtro __gt=0 + F() dejan la condición y
    # la resta en un solo UPDATE, así que dos despachos concurrentes no lo pasan a -1.
    Company.objects.filter(
        pk=instance.company_id, trial_shipments_remaining__gt=0
    ).update(trial_shipments_remaining=F("trial_shipments_remaining") - 1)

    # UsageLog del mes del despacho.
    increment_usage(instance.company_id, "shipments_created", instance.dispatched_at)

    # El email se dispara recién cuando la transacción commitea: si el despacho se
    # revierte, no queda un email avisando de un remito que nunca se despachó.
    # send_dispatch_email() no levanta excepciones (ver shipments/emails.py): un fallo
    # de Resend no puede romper la respuesta de un despacho ya commiteado.
    transaction.on_commit(lambda: send_dispatch_email(instance))


@receiver(post_save, sender=Evidence)
def on_evidence_uploaded(sender, instance, created, **kwargs):
    """Suma la foto al UsageLog del mes (sección 6: se actualiza vía signal).

    Solo en el alta: editar un Evidence existente no cuenta como una foto nueva. Se
    cuenta tanto la evidencia de despacho como la de recepción, porque ambas son una
    foto guardada en R2 para esa empresa.
    """
    if not created:
        return

    increment_usage(
        instance.shipment.company_id, "photos_uploaded", instance.uploaded_at
    )
