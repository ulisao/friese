from django.contrib import admin

from .models import Company, UsageLog


@admin.register(Company)
class CompanyAdmin(admin.ModelAdmin):
    """Empresa (tenant). Ver docs/desarrollo.md sección 3."""

    list_display = ("name", "email", "plan", "is_active", "trial_shipments_remaining", "created_at")
    list_filter = ("is_active", "plan")
    search_fields = ("name", "email")
    readonly_fields = ("created_at",)


@admin.register(UsageLog)
class UsageLogAdmin(admin.ModelAdmin):
    """Consumo mensual por empresa. Solo lectura: el spec (sección 6) exige que
    se actualice únicamente vía signals, nunca a mano. Ver docs/desarrollo.md.
    """

    list_display = ("company", "month", "shipments_created", "photos_uploaded", "emails_sent")
    list_filter = ("month", "company")
    search_fields = ("company__name", "month")
    readonly_fields = ("company", "month", "shipments_created", "photos_uploaded", "emails_sent")

    def has_add_permission(self, request):
        return False
