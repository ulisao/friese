from django.db import models
from simple_history.models import HistoricalRecords


class SupportTicket(models.Model):
    """Pedido de soporte de una empresa a Friese (tarea 9.1).

    Lo crea el admin de la empresa desde SU panel (el Django Admin, aislado por
    empresa como el resto del sistema — ver `companies/admin_mixins.py` y la
    tarea 4.1) y lo atiende el superadmin de Friese. No hay endpoint de API ni
    pantalla propia en el frontend: el canal es el panel.

    El `status` lo mueve SOLO Friese: quien abre el ticket no decide si está
    resuelto. Eso se hace en `SupportTicketAdmin`, no en el modelo, porque es
    una regla de quién puede editar qué, no del dato.
    """

    OPEN = "open"
    IN_PROGRESS = "in_progress"
    RESOLVED = "resolved"
    CLOSED = "closed"
    STATUS_CHOICES = [
        (OPEN, "Abierto"),
        (IN_PROGRESS, "En curso"),
        (RESOLVED, "Resuelto"),
        (CLOSED, "Cerrado"),
    ]

    company = models.ForeignKey(
        "companies.Company",
        on_delete=models.CASCADE,
        related_name="support_tickets",
        verbose_name="Empresa",
    )
    # PROTECT como `Shipment.operator`: un usuario que abrió un ticket no se
    # borra, se desactiva. Si se borrara, el ticket quedaría sin autor y el
    # historial de la conversación pierde la mitad de su sentido.
    created_by = models.ForeignKey(
        "users.User",
        on_delete=models.PROTECT,
        related_name="support_tickets",
        verbose_name="Abierto por",
    )
    subject = models.CharField("Asunto", max_length=200)
    description = models.TextField("Descripción")
    status = models.CharField(
        "Estado", max_length=20, choices=STATUS_CHOICES, default=OPEN
    )
    created_at = models.DateTimeField("Fecha de creación", auto_now_add=True)
    updated_at = models.DateTimeField("Última modificación", auto_now=True)

    # Historial de cambios (tarea 8.2). Acá cumple una función puntual: la
    # empresa puede AMPLIAR la descripción de su propio ticket editándolo (no
    # hay modelo de comentarios aparte), así que sin historial el texto original
    # se perdería en cada edición. Con esto queda cada versión, con su autor y su
    # fecha, y de paso el rastro de quién movió el estado.
    history = HistoricalRecords(
        verbose_name="historial de ticket",
        verbose_name_plural="historial de tickets",
    )

    class Meta:
        # El ticket más nuevo primero: es el orden en que se atienden.
        ordering = ("-created_at",)
        verbose_name = "Ticket de soporte"
        verbose_name_plural = "Tickets de soporte"

    def __str__(self):
        return f"#{self.pk} — {self.subject}"
