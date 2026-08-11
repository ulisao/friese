from django.contrib import admin
from django.utils.html import format_html

from companies.admin_mixins import CompanyScopedAdminMixin

from .models import Evidence, Shipment, ShipmentItem


class ShipmentItemInline(CompanyScopedAdminMixin, admin.TabularInline):
    """Ítems del remito, editables desde la ficha del Shipment."""

    company_lookup = "shipment__company"
    company_fk_lookups = {"product": "company"}

    model = ShipmentItem
    extra = 0
    autocomplete_fields = ("product",)


class EvidenceInline(CompanyScopedAdminMixin, admin.TabularInline):
    """Evidencia del remito, visible desde la ficha del Shipment.

    Las fotos se muestran EMBEBIDAS (miniatura) para no tener que abrir la URL de R2
    aparte. `file_url` apunta al bucket público (tarea 2.4), así que el navegador la
    carga directo.
    """

    company_lookup = "shipment__company"
    company_fk_lookups = {"shipment_item": "shipment__company", "uploaded_by": "company"}

    model = Evidence
    extra = 0
    # Primero las de despacho ('dispatch' < 'reception') y, dentro de cada tipo, en
    # orden cronológico: es el orden en que ocurrieron las dos mitades del remito.
    ordering = ("type", "uploaded_at")
    fields = ("preview", "type", "shipment_item", "uploaded_by", "file_url", "uploaded_at")
    readonly_fields = ("preview", "uploaded_at")

    @admin.display(description="Foto")
    def preview(self, obj):
        if obj is None or not obj.file_url:
            return "—"
        # La miniatura linkea a la imagen completa (nueva pestaña) para mirar el detalle.
        # El límite manda por ancho: las fotos vienen de la cámara del celular, casi
        # siempre verticales, y acotarlas por alto las dejaba de 90px (ilegibles).
        return format_html(
            '<a href="{0}" target="_blank" rel="noopener">'
            '<img src="{0}" alt="Evidencia" '
            'style="max-width:200px;max-height:300px;border-radius:4px;"></a>',
            obj.file_url,
        )


@admin.register(Shipment)
class ShipmentAdmin(CompanyScopedAdminMixin, admin.ModelAdmin):
    """Remito. Ver docs/desarrollo.md sección 3."""

    company_fk_lookups = {"company": "pk", "operator": "company"}

    list_display = (
        "id",
        "company",
        "operator",
        "receiver_name",
        "status",
        "auto_closed",
        "created_at",
    )
    # auto_closed en el filtro: con status=accepted permite separar la conformidad
    # expresa del receptor del cierre por silencio a las 48hs (tarea 3.3).
    # created_at con DateFieldListFilter: rangos de fecha (hoy / últimos 7 días / este
    # mes / este año) combinables con el filtro de estado.
    list_filter = (
        "status",
        ("created_at", admin.DateFieldListFilter),
        "auto_closed",
        "company",
    )
    # Navegación por año → mes → día arriba del listado: cubre la fecha exacta o el mes
    # puntual, que los rangos fijos de list_filter no alcanzan.
    date_hierarchy = "created_at"
    search_fields = ("receiver_name", "receiver_email")
    # Autogenerados o escritos por el receptor / las tareas periódicas: no editables
    # a mano. reminder_sent_at lo escribe solo send_pending_reminders (tarea 5.2);
    # tocarlo desde acá mandaría (o suprimiría) un recordatorio.
    readonly_fields = (
        "public_token",
        "created_at",
        "dispute_reason",
        "auto_closed",
        "reminder_sent_at",
    )
    autocomplete_fields = ("company", "operator")
    inlines = (ShipmentItemInline, EvidenceInline)


@admin.register(ShipmentItem)
class ShipmentItemAdmin(CompanyScopedAdminMixin, admin.ModelAdmin):
    """Ítem de remito (producto + cantidad). Ver docs/desarrollo.md sección 3."""

    company_lookup = "shipment__company"
    company_fk_lookups = {"shipment": "company", "product": "company"}

    list_display = ("shipment", "product", "quantity")
    search_fields = ("product__name",)
    autocomplete_fields = ("shipment", "product")


@admin.register(Evidence)
class EvidenceAdmin(CompanyScopedAdminMixin, admin.ModelAdmin):
    """Foto de evidencia de un remito. Ver docs/desarrollo.md sección 3."""

    company_lookup = "shipment__company"
    company_fk_lookups = {
        "shipment": "company",
        "shipment_item": "shipment__company",
        "uploaded_by": "company",
    }

    list_display = ("id", "shipment", "shipment_item", "type", "uploaded_by", "uploaded_at")
    list_filter = ("type",)
    readonly_fields = ("uploaded_at",)
    autocomplete_fields = ("shipment", "shipment_item", "uploaded_by")
