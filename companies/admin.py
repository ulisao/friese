from django.contrib import admin

from .admin_mixins import CompanyScopedAdminMixin
from .forms import CompanyWithFirstAdminForm
from .models import Company, UsageLog


@admin.register(Company)
class CompanyAdmin(CompanyScopedAdminMixin, admin.ModelAdmin):
    """Empresa (tenant). Ver docs/desarrollo.md sección 3.

    El admin de una empresa solo ve su propia ficha; el superadmin las ve todas.
    El ALTA es del superadmin de Friese y crea la empresa junto con su primer
    admin en un solo formulario (tarea 4.4).
    """

    # Company ES el tenant: el filtro va contra su propia PK.
    company_lookup = "pk"

    list_display = ("name", "email", "plan", "is_active", "trial_shipments_remaining", "created_at")
    list_filter = ("is_active", "plan")
    search_fields = ("name", "email")
    ordering = ("name",)
    readonly_fields = ("created_at",)

    # Campos que decide Friese, no el cliente: el admin de la empresa los ve en
    # su ficha pero no puede editarlos (su propio trial y su plan son
    # facturación, y desactivarse a sí misma tampoco es decisión suya).
    friese_only_fields = ("plan", "is_active", "trial_shipments_remaining")

    # Alta de empresa + primer admin en una sola pantalla.
    add_form = CompanyWithFirstAdminForm
    add_fieldsets = (
        (
            "Empresa",
            {"fields": ("name", "email", "phone", "plan", "is_active")},
        ),
        (
            "Facturación",
            {
                "fields": ("trial_shipments_remaining",),
                "description": (
                    "Toda empresa nueva arranca con 10 remitos de trial. Cada "
                    "despacho descuenta 1; al llegar a 0 los remitos siguientes "
                    "cuentan para facturación según el tier del mes."
                ),
            },
        ),
        (
            "Primer admin de la empresa",
            {
                "fields": (
                    "admin_username",
                    "admin_email",
                    "admin_password",
                    "admin_password_confirm",
                ),
                "description": (
                    "Se crea junto con la empresa, con acceso a este panel "
                    "limitado a los datos de la empresa. Después él mismo da de "
                    "alta a sus operadores desde Users. La contraseña hay que "
                    "entregársela por fuera del sistema."
                ),
            },
        ),
    )

    def get_fieldsets(self, request, obj=None):
        if obj is None:
            return self.add_fieldsets
        return super().get_fieldsets(request, obj)

    def get_form(self, request, obj=None, change=False, **kwargs):
        if obj is None:
            kwargs["form"] = self.add_form
        return super().get_form(request, obj, change=change, **kwargs)

    def get_readonly_fields(self, request, obj=None):
        readonly_fields = super().get_readonly_fields(request, obj)
        if request.user.is_superuser:
            return readonly_fields
        return tuple(readonly_fields) + self.friese_only_fields

    def has_add_permission(self, request):
        # Solo Friese da de alta empresas: una empresa creada por un admin de
        # empresa quedaría fuera de su propio tenant (get_queryset filtra por su
        # propia pk), o sea invisible para quien la creó.
        return request.user.is_superuser and super().has_add_permission(request)

    def save_model(self, request, obj, form, change):
        super().save_model(request, obj, form, change)
        if not change:
            # El admin envuelve el alta en una transacción: si esto falla, la
            # empresa tampoco queda creada.
            user = form.create_first_admin(obj)
            self.message_user(
                request,
                f"Se creó el admin «{user.username}» de {obj.name}, con acceso a "
                f"este panel. Pasale la contraseña por fuera del sistema.",
            )


@admin.register(UsageLog)
class UsageLogAdmin(CompanyScopedAdminMixin, admin.ModelAdmin):
    """Consumo mensual por empresa. Solo lectura: el spec (sección 6) exige que
    se actualice únicamente vía signals, nunca a mano. Ver docs/desarrollo.md.
    """

    list_display = (
        "company",
        "month",
        "shipments_created",
        "photos_uploaded",
        "emails_sent",
        "tier",
    )
    list_filter = ("month", "company")
    search_fields = ("company__name", "month")
    readonly_fields = (
        "company",
        "month",
        "shipments_created",
        "photos_uploaded",
        "emails_sent",
        "tier",
    )
    # El mes más reciente primero; dentro del mes, las empresas por nombre.
    ordering = ("-month", "company__name")

    def has_add_permission(self, request):
        return False

    @admin.display(description="Tier", ordering="shipments_created")
    def tier(self, obj):
        """Tier de facturación del mes (docs/Desarrollo.md sección 6).

        El cálculo vive en el modelo; acá solo se muestra. Se ordena por
        shipments_created, que es de donde sale el tier.
        """
        return obj.tier or "—"
