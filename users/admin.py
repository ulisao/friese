from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as DjangoUserAdmin
from rest_framework_simplejwt.token_blacklist.admin import (
    BlacklistedTokenAdmin as SimpleJWTBlacklistedTokenAdmin,
)
from rest_framework_simplejwt.token_blacklist.admin import (
    OutstandingTokenAdmin as SimpleJWTOutstandingTokenAdmin,
)
from rest_framework_simplejwt.token_blacklist.models import BlacklistedToken, OutstandingToken

from companies.admin_mixins import CompanyScopedAdminMixin

from .groups import ensure_company_admin_group
from .models import OperatorInvite, User


@admin.register(User)
class UserAdmin(CompanyScopedAdminMixin, DjangoUserAdmin):
    """User extendido. Reusa el UserAdmin nativo (maneja el hash de password)
    y agrega company + role. Ver docs/desarrollo.md sección 3.

    El acceso al panel se deriva del `role` (tarea 4.4): role=admin queda staff
    y en el grupo "Admin de empresa"; role=operator no entra al panel (usa la app
    de React).
    """

    company_fk_lookups = {"company": "pk"}

    # Campos que solo maneja el superadmin de Friese. `is_superuser`, `groups` y
    # `user_permissions` son escalada de privilegios (con ellos un admin de
    # empresa se sale de su tenant). `company` la fija el propio tenant, y
    # `is_staff` se deriva del role: verlos editables sería engañoso.
    superuser_only_fields = (
        "company",
        "is_staff",
        "is_superuser",
        "groups",
        "user_permissions",
    )

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

    def get_fieldsets(self, request, obj=None):
        fieldsets = super().get_fieldsets(request, obj)
        if request.user.is_superuser:
            return fieldsets
        cleaned = []
        for name, opts in fieldsets:
            fields = tuple(
                f for f in opts.get("fields", ()) if f not in self.superuser_only_fields
            )
            if fields:
                cleaned.append((name, {**opts, "fields": fields}))
        return cleaned

    def save_model(self, request, obj, form, change):
        if not request.user.is_superuser:
            # Un admin de empresa solo da de alta usuarios DENTRO de su empresa
            # (el campo `company` ni aparece en su formulario).
            obj.company_id = request.user.company_id
        if not obj.is_superuser:
            # El acceso al panel lo decide el role. Un role vacío no se toca: es
            # un usuario que no es ni admin ni operador de una empresa.
            if obj.role == User.ADMIN:
                obj.is_staff = True
            elif obj.role == User.OPERATOR:
                obj.is_staff = False
        super().save_model(request, obj, form, change)

    def save_related(self, request, form, formsets, change):
        # Los grupos se ajustan DESPUÉS de que el form guarde sus m2m: si no, el
        # `groups` del formulario del superadmin pisaría lo de acá.
        super().save_related(request, form, formsets, change)
        user = form.instance
        if user.is_superuser:
            return
        group = ensure_company_admin_group()
        if user.role == User.ADMIN:
            user.groups.add(group)
        elif user.role == User.OPERATOR:
            user.groups.remove(group)


@admin.register(OperatorInvite)
class OperatorInviteAdmin(CompanyScopedAdminMixin, admin.ModelAdmin):
    """Invitación de alta de operador. El token se autogenera al guardar y es
    el que va en el QR. Ver docs/desarrollo.md secciones 3 y 4.
    """

    company_fk_lookups = {"company": "pk"}

    list_display = ("token", "company", "is_used", "created_at", "expires_at")
    list_filter = ("is_used", "company")
    search_fields = ("token",)
    # token: editable=False + default uuid4 → aparece (readonly) recién al guardar.
    readonly_fields = ("token", "created_at")
    autocomplete_fields = ("company",)


# Los admins de los tokens JWT los registra simplejwt (app token_blacklist). Se
# reemplazan por versiones scopeadas: la sección 4 pide que el admin de la empresa
# pueda revocar el refresh token de UN operador puntual, y para eso no tiene que ver
# —ni poder blacklistear— los tokens de los operadores de otra empresa.
admin.site.unregister(OutstandingToken)
admin.site.unregister(BlacklistedToken)


@admin.register(OutstandingToken)
class OutstandingTokenAdmin(CompanyScopedAdminMixin, SimpleJWTOutstandingTokenAdmin):
    company_lookup = "user__company"


@admin.register(BlacklistedToken)
class BlacklistedTokenAdmin(CompanyScopedAdminMixin, SimpleJWTBlacklistedTokenAdmin):
    company_lookup = "token__user__company"
    company_fk_lookups = {"token": "user__company"}
