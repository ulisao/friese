from django.db import models


class Product(models.Model):
    """Producto del catálogo de una empresa. Ver docs/desarrollo.md sección 3."""

    BOLSAS = "bolsas"
    KG = "kg"
    M3 = "m3"
    TON = "ton"
    UNIDAD = "unidad"
    UNIT_CHOICES = [
        (BOLSAS, "Bolsas"),
        (KG, "Kg"),
        (M3, "m3"),
        (TON, "Ton"),
        (UNIDAD, "Unidad"),
    ]

    company = models.ForeignKey(
        "companies.Company",
        on_delete=models.CASCADE,
        related_name="products",
    )
    name = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    barcode = models.CharField(max_length=255, null=True, blank=True)
    is_active = models.BooleanField(default=True)
    # Obligatorio, choices fijas (no texto libre).
    unit = models.CharField(max_length=20, choices=UNIT_CHOICES)

    def __str__(self):
        return f"{self.name} ({self.get_unit_display()})"
