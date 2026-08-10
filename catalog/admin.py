from django.contrib import admin

from companies.admin_mixins import CompanyScopedAdminMixin

from .models import Product


@admin.register(Product)
class ProductAdmin(CompanyScopedAdminMixin, admin.ModelAdmin):
    """Producto del catálogo. Ver docs/desarrollo.md sección 3."""

    company_fk_lookups = {"company": "pk"}

    list_display = ("name", "company", "unit", "barcode", "is_active")
    list_filter = ("unit", "is_active", "company")
    search_fields = ("name", "barcode")
    autocomplete_fields = ("company",)
