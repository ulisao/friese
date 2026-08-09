from django.db import models


class Shipment(models.Model):
    """Remito con evidencia de despacho/recepción. Ver docs/desarrollo.md sección 3."""

    DRAFT = "draft"
    DISPATCHED = "dispatched"
    ACCEPTED = "accepted"
    DISPUTED = "disputed"
    CLOSED = "closed"
    STATUS_CHOICES = [
        (DRAFT, "Draft"),
        (DISPATCHED, "Dispatched"),
        (ACCEPTED, "Accepted"),
        (DISPUTED, "Disputed"),
        (CLOSED, "Closed"),
    ]

    company = models.ForeignKey(
        "companies.Company",
        on_delete=models.CASCADE,
        related_name="shipments",
    )
    operator = models.ForeignKey(
        "users.User",
        on_delete=models.PROTECT,
        related_name="shipments",
    )
    receiver_name = models.CharField(max_length=255)
    receiver_email = models.EmailField(blank=True)
    receiver_phone = models.CharField(max_length=50, blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=DRAFT)
    dispatched_at = models.DateTimeField(null=True, blank=True)
    # NO se genera al crear: queda null hasta el despacho (tarea 2.3).
    public_token = models.UUIDField(null=True, blank=True, unique=True, editable=False)
    link_opened_at = models.DateTimeField(null=True, blank=True)
    response_deadline = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Shipment #{self.pk} ({self.get_status_display()})"


class ShipmentItem(models.Model):
    """Ítem (producto + cantidad) de un remito. Ver docs/desarrollo.md sección 3."""

    shipment = models.ForeignKey(
        Shipment,
        on_delete=models.CASCADE,
        related_name="items",
    )
    product = models.ForeignKey(
        "catalog.Product",
        on_delete=models.PROTECT,
        related_name="shipment_items",
    )
    quantity = models.DecimalField(max_digits=12, decimal_places=2)
    notes = models.TextField(blank=True)

    def __str__(self):
        return f"{self.quantity} x {self.product} (Shipment #{self.shipment_id})"


class Evidence(models.Model):
    """Foto de evidencia de un remito. Ver docs/desarrollo.md sección 3."""

    DISPATCH = "dispatch"
    RECEPTION = "reception"
    TYPE_CHOICES = [
        (DISPATCH, "Dispatch"),
        (RECEPTION, "Reception"),
    ]

    shipment = models.ForeignKey(
        Shipment,
        on_delete=models.CASCADE,
        related_name="evidence",
    )
    type = models.CharField(max_length=20, choices=TYPE_CHOICES)
    # Nullable: el receptor (sin login) también sube evidencia.
    uploaded_by = models.ForeignKey(
        "users.User",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="evidence",
    )
    file_url = models.URLField(max_length=1000)
    # Timestamp del servidor: fuente de verdad de la evidencia.
    uploaded_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Evidence {self.get_type_display()} (Shipment #{self.shipment_id})"
