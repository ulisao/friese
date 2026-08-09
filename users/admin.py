from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as DjangoUserAdmin

from .models import OperatorInvite, User


@admin.register(User)
class UserAdmin(DjangoUserAdmin):
    """User extendido. Reusa el UserAdmin nativo (maneja el hash de password)
    y agrega company + role. Ver docs/desarrollo.md sección 3.
    """

    # Se agrega la sección "Friese" a los fieldsets nativos.
    fieldsets = DjangoUserAdmin.fieldsets + (
        ("Friese", {"fields": ("company", "role")}),
    )
    add_fieldsets = DjangoUserAdmin.add_fieldsets + (
        ("Friese", {"fields": ("company", "role")}),
    )
    list_display = ("username", "email", "company", "role", "is_active", "is_superuser")
    list_filter = DjangoUserAdmin.list_filter + ("company", "role")
    autocomplete_fields = ("company",)


@admin.register(OperatorInvite)
class OperatorInviteAdmin(admin.ModelAdmin):
    """Invitación de alta de operador. El token se autogenera al guardar y es
    el que va en el QR. Ver docs/desarrollo.md secciones 3 y 4.
    """

    list_display = ("token", "company", "is_used", "created_at", "expires_at")
    list_filter = ("is_used", "company")
    search_fields = ("token",)
    # token: editable=False + default uuid4 → aparece (readonly) recién al guardar.
    readonly_fields = ("token", "created_at")
    autocomplete_fields = ("company",)
