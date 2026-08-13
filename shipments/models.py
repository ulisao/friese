from django.db import models


class Shipment(models.Model):
    """Remito con evidencia de despacho/recepción. Ver docs/desarrollo.md sección 3."""

    DRAFT = "draft"
    DISPATCHED = "dispatched"
    ACCEPTED = "accepted"
    DISPUTED = "disputed"
    CLOSED = "closed"
    # Las etiquetas son las MISMAS que muestra el frontend
    # (frontend/src/lib/shipmentStatus.js): el estado tiene que leerse igual en el
    # panel y en la app del operador.
    STATUS_CHOICES = [
        (DRAFT, "Borrador"),
        (DISPATCHED, "Despachado"),
        (ACCEPTED, "Aceptado"),
        (DISPUTED, "En disputa"),
        (CLOSED, "Cerrado"),
    ]

    company = models.ForeignKey(
        "companies.Company",
        on_delete=models.CASCADE,
        related_name="shipments",
        verbose_name="Empresa",
    )
    operator = models.ForeignKey(
        "users.User",
        on_delete=models.PROTECT,
        related_name="shipments",
        verbose_name="Operador",
    )
    receiver_name = models.CharField("Receptor", max_length=255)
    receiver_email = models.EmailField("Email del receptor", blank=True)
    receiver_phone = models.CharField(
        "Teléfono del receptor", max_length=50, blank=True
    )
    status = models.CharField(
        "Estado", max_length=20, choices=STATUS_CHOICES, default=DRAFT
    )
    dispatched_at = models.DateTimeField("Despachado el", null=True, blank=True)
    # NO se genera al crear: queda null hasta el despacho (tarea 2.3).
    public_token = models.UUIDField(
        "Token del link público", null=True, blank=True, unique=True, editable=False
    )
    link_opened_at = models.DateTimeField(
        "Link abierto por el receptor el", null=True, blank=True
    )
    response_deadline = models.DateTimeField(
        "Plazo de respuesta", null=True, blank=True
    )
    created_at = models.DateTimeField("Fecha de creación", auto_now_add=True)
    # Texto opcional con el que el receptor explica la queja (tarea 3.2). Solo lo
    # escribe el endpoint público de dispute; vacío en cualquier otro estado.
    dispute_reason = models.TextField("Motivo de la queja", blank=True)
    # True = el remito quedó en 'accepted' por el cierre automático a las 48hs
    # (tarea 3.3), no porque el receptor lo haya aceptado. Permite distinguir la
    # conformidad expresa del silencio del cliente. Lo escribe únicamente la tarea
    # periódica close_expired_shipments.
    auto_closed = models.BooleanField("Cerrado automáticamente", default=False)
    # Momento en que se le mandó al receptor el recordatorio por no haber abierto el
    # link (tarea 5.2). Null = todavía no se le mandó. Es la marca que garantiza que
    # el recordatorio salga UNA SOLA VEZ, por más veces que corra la tarea periódica.
    # Lo escribe únicamente el comando send_pending_reminders.
    reminder_sent_at = models.DateTimeField(
        "Recordatorio enviado el", null=True, blank=True
    )

    class Meta:
        verbose_name = "Remito"
        verbose_name_plural = "Remitos"

    def __str__(self):
        return f"Remito #{self.pk} ({self.get_status_display()})"


class ShipmentItem(models.Model):
    """Ítem (producto + cantidad) de un remito. Ver docs/desarrollo.md sección 3."""

    shipment = models.ForeignKey(
        Shipment,
        on_delete=models.CASCADE,
        related_name="items",
        verbose_name="Remito",
    )
    product = models.ForeignKey(
        "catalog.Product",
        on_delete=models.PROTECT,
        related_name="shipment_items",
        verbose_name="Producto",
    )
    quantity = models.DecimalField("Cantidad", max_digits=12, decimal_places=2)
    notes = models.TextField("Notas", blank=True)

    class Meta:
        verbose_name = "Ítem del remito"
        verbose_name_plural = "Ítems del remito"

    def __str__(self):
        return f"{self.quantity} x {self.product} (Remito #{self.shipment_id})"


class Evidence(models.Model):
    """Foto de evidencia de un remito. Ver docs/desarrollo.md sección 3."""

    DISPATCH = "dispatch"
    RECEPTION = "reception"
    TYPE_CHOICES = [
        (DISPATCH, "Despacho"),
        (RECEPTION, "Recepción"),
    ]

    shipment = models.ForeignKey(
        Shipment,
        on_delete=models.CASCADE,
        related_name="evidence",
        verbose_name="Remito",
    )
    # Opcional: la foto puede documentar un producto concreto del remito o el remito
    # completo (tarea 3.2). SET_NULL para no perder la evidencia si el ítem se borra
    # mientras el remito todavía es un draft.
    shipment_item = models.ForeignKey(
        ShipmentItem,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="evidence",
        verbose_name="Ítem del remito",
    )
    type = models.CharField("Tipo", max_length=20, choices=TYPE_CHOICES)
    # Nullable: el receptor (sin login) también sube evidencia.
    uploaded_by = models.ForeignKey(
        "users.User",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="evidence",
        verbose_name="Subida por",
    )
    file_url = models.URLField("URL de la foto", max_length=1000)
    # Timestamp del servidor: fuente de verdad de la evidencia.
    uploaded_at = models.DateTimeField("Fecha de subida", auto_now_add=True)

    class Meta:
        verbose_name = "Evidencia"
        verbose_name_plural = "Evidencia"

    def __str__(self):
        return f"Evidencia de {self.get_type_display().lower()} (Remito #{self.shipment_id})"
