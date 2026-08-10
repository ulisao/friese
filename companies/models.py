from django.db import models


class Company(models.Model):
    """Empresa registrada en Friese (tenant). Ver docs/desarrollo.md sección 3."""

    name = models.CharField(max_length=255)
    email = models.EmailField()
    phone = models.CharField(max_length=50, blank=True)
    plan = models.CharField(max_length=50, blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    # Remitos gratis restantes antes de empezar a facturar (trial).
    trial_shipments_remaining = models.IntegerField(default=10)

    class Meta:
        verbose_name = "Company"
        verbose_name_plural = "Companies"

    def __str__(self):
        return self.name


class UsageLog(models.Model):
    """Consumo mensual por empresa. Ver docs/desarrollo.md sección 3.

    Se actualiza únicamente vía signals de Django (tarea 2.3), nunca a mano.
    """

    # Tiers de facturación (docs/Desarrollo.md sección 6): se calculan sobre
    # shipments_created del mes. 1-50 = Arranque, 51-200 = Crecimiento, 201+ =
    # Volumen. Es un cálculo de LECTURA para reportes del superadmin: no se
    # guarda en la DB ni bloquea nada del producto.
    TIER_ARRANQUE = "Arranque"
    TIER_CRECIMIENTO = "Crecimiento"
    TIER_VOLUMEN = "Volumen"
    TIER_ARRANQUE_MAX = 50
    TIER_CRECIMIENTO_MAX = 200

    company = models.ForeignKey(
        Company,
        on_delete=models.CASCADE,
        related_name="usage_logs",
    )
    # Mes de consumo, formato "YYYY-MM".
    month = models.CharField(max_length=7)
    shipments_created = models.IntegerField(default=0)
    photos_uploaded = models.IntegerField(default=0)
    emails_sent = models.IntegerField(default=0)

    class Meta:
        # Un único registro de consumo por empresa y mes.
        unique_together = ("company", "month")

    @property
    def tier(self):
        """Tier de facturación del mes, derivado de shipments_created.

        Devuelve None si la empresa no despachó ningún remito en el mes: los
        tiers arrancan en 1 remito, así que un mes en 0 no cae en ninguno (el
        UsageLog puede existir igual, por ejemplo si solo se subieron fotos).
        """
        if self.shipments_created < 1:
            return None
        if self.shipments_created <= self.TIER_ARRANQUE_MAX:
            return self.TIER_ARRANQUE
        if self.shipments_created <= self.TIER_CRECIMIENTO_MAX:
            return self.TIER_CRECIMIENTO
        return self.TIER_VOLUMEN

    def __str__(self):
        return f"{self.company} — {self.month}"
