from django.contrib import admin

from .models import Evidence, Shipment, ShipmentItem


class ShipmentItemInline(admin.TabularInline):
    """Ítems del remito, editables desde la ficha del Shipment."""

    model = ShipmentItem
    extra = 0
    autocomplete_fields = ("product",)


class EvidenceInline(admin.TabularInline):
    """Evidencia del remito, visible desde la ficha del Shipment."""

    model = Evidence
    extra = 0
    readonly_fields = ("uploaded_at",)


@admin.register(Shipment)
class ShipmentAdmin(admin.ModelAdmin):
    """Remito. Ver docs/desarrollo.md sección 3."""

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
    list_filter = ("status", "auto_closed", "company")
    search_fields = ("receiver_name", "receiver_email")
    # Autogenerados o escritos por el receptor / la tarea periódica: no editables a mano.
    readonly_fields = ("public_token", "created_at", "dispute_reason", "auto_closed")
    autocomplete_fields = ("company", "operator")
    inlines = (ShipmentItemInline, EvidenceInline)


@admin.register(ShipmentItem)
class ShipmentItemAdmin(admin.ModelAdmin):
    """Ítem de remito (producto + cantidad). Ver docs/desarrollo.md sección 3."""

    list_display = ("shipment", "product", "quantity")
    search_fields = ("product__name",)
    autocomplete_fields = ("shipment", "product")


@admin.register(Evidence)
class EvidenceAdmin(admin.ModelAdmin):
    """Foto de evidencia de un remito. Ver docs/desarrollo.md sección 3."""

    list_display = ("id", "shipment", "shipment_item", "type", "uploaded_by", "uploaded_at")
    list_filter = ("type",)
    readonly_fields = ("uploaded_at",)
    autocomplete_fields = ("shipment", "shipment_item", "uploaded_by")
