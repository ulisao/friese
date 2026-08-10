"""Aislamiento multi-tenant del Django Admin.

Ver docs/Desarrollo.md sección 1.4 ("Cada empresa accede solo a sus datos mediante
sobreescritura de get_queryset() en cada ModelAdmin. El superadmin (Friese) tiene
acceso total") y sección 2.2 (el aislamiento es a nivel de aplicación).
"""


class CompanyScopedAdminMixin:
    """Restringe un ModelAdmin (o un InlineModelAdmin) a la empresa del usuario.

    El superadmin de Friese (`is_superuser`) sigue viendo TODO, sin filtro. Cualquier
    otro usuario del admin ve y edita únicamente las filas de su propia `company`; si
    no tiene empresa asignada, no ve nada.

    Atributos de configuración por admin:

    - `company_lookup`: ruta desde el modelo administrado hasta Company
      (p. ej. `"shipment__company"` en ShipmentItem, `"pk"` en el propio Company).
    - `company_fk_lookups`: por cada FK editable del formulario, la ruta desde el
      modelo APUNTADO hasta Company. Sin esto `get_queryset()` aísla lo que se ve,
      pero los desplegables del formulario seguirían permitiendo crear una fila
      dentro de otra empresa o mover una propia hacia ella.
    - `superuser_only_list_filters`: filtros del listado que se ocultan al admin de
      empresa. El desplegable de un filtro por FK lista TODAS las filas relacionadas
      (todas las empresas), así que filtrar por `company` filtraría bien pero
      mostraría los nombres de las demás empresas.
    """

    company_lookup = "company"
    company_fk_lookups = {}
    superuser_only_list_filters = ("company",)

    def get_queryset(self, request, *args, **kwargs):
        qs = super().get_queryset(request, *args, **kwargs)
        if request.user.is_superuser:
            return qs
        company_id = getattr(request.user, "company_id", None)
        if company_id is None:
            # Usuario del admin sin empresa y que no es el superadmin: no pertenece
            # a ningún tenant, así que no le corresponde ninguna fila.
            return qs.none()
        return qs.filter(**{self.company_lookup: company_id})

    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        if not request.user.is_superuser and db_field.name in self.company_fk_lookups:
            company_id = getattr(request.user, "company_id", None)
            manager = db_field.remote_field.model._default_manager
            lookup = self.company_fk_lookups[db_field.name]
            kwargs["queryset"] = (
                manager.none()
                if company_id is None
                else manager.filter(**{lookup: company_id})
            )
        return super().formfield_for_foreignkey(db_field, request, **kwargs)

    def get_list_filter(self, request):
        list_filter = super().get_list_filter(request)
        if request.user.is_superuser:
            return list_filter
        return tuple(f for f in list_filter if f not in self.superuser_only_list_filters)
