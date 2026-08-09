from django.contrib import admin

from .models import Product


@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    """Producto del catálogo. Ver docs/desarrollo.md sección 3."""

    list_display = ("name", "company", "unit", "barcode", "is_active")
    list_filter = ("unit", "is_active", "company")
    search_fields = ("name", "barcode")
    autocomplete_fields = ("company",)
