from django import forms
from django.contrib import admin
from django.utils.safestring import mark_safe

from companies.admin_mixins import CompanyScopedAdminMixin

from .models import Product


class BarcodeScanWidget(forms.TextInput):
    """Input de `barcode` + botón "Escanear código" con la cámara.

    Hoy el admin de empresa tiene que tipear el código a mano; el botón abre
    la cámara y decodifica QR/EAN en vivo (ver static/admin/js/barcode_scan.js),
    y solo llena el campo cuando el admin confirma lo que se leyó — nunca
    guarda solo. El JS ubica el input por `data-barcode-scan-input`.
    """

    class Media:
        css = {"all": ("admin/css/barcode_scan.css",)}
        js = (
            "admin/js/vendor/jsQR.js",
            "admin/js/vendor/quagga.min.js",
            "admin/js/barcode_scan.js",
        )

    def render(self, name, value, attrs=None, renderer=None):
        attrs = dict(attrs or {})
        attrs["data-barcode-scan-input"] = "1"
        input_html = super().render(name, value, attrs, renderer)
        button_html = (
            '<button type="button" class="button" data-barcode-scan-trigger="1">'
            "Escanear código"
            "</button>"
        )
        return mark_safe(f'<div class="barcode-scan-field">{input_html}{button_html}</div>')


class ProductAdminForm(forms.ModelForm):
    class Meta:
        model = Product
        fields = "__all__"
        widgets = {"barcode": BarcodeScanWidget}


@admin.register(Product)
class ProductAdmin(CompanyScopedAdminMixin, admin.ModelAdmin):
    """Producto del catálogo. Ver docs/desarrollo.md sección 3."""

    form = ProductAdminForm
    company_fk_lookups = {"company": "pk"}

    list_display = ("name", "company", "unit", "barcode", "is_active")
    list_filter = ("unit", "is_active", "company")
    search_fields = ("name", "barcode")
    autocomplete_fields = ("company",)
