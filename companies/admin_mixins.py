"""Aislamiento multi-tenant del Django Admin.

Ver docs/Desarrollo.md sección 1.4 ("Cada empresa accede solo a sus datos mediante
sobreescritura de get_queryset() en cada ModelAdmin. El superadmin (Friese) tiene
acceso total") y sección 2.2 (el aislamiento es a nivel de aplicación).
"""

from django.core.exceptions import PermissionDenied
from django.http import Http404
from simple_history.admin import SimpleHistoryAdmin


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


class CompanyScopedHistoryAdmin(CompanyScopedAdminMixin, SimpleHistoryAdmin):
    """ModelAdmin con historial de cambios (tarea 8.2) y aislado por empresa.

    `SimpleHistoryAdmin` agrega el botón "Historial" de la ficha y dos vistas:
    el listado de versiones y el detalle de una versión puntual. Ninguna de las
    dos pasa por `get_queryset()`, así que ninguna hereda el aislamiento del
    mixin — hay que atarlas a mano, y es lo que hace esta clase:

    1. El listado (`history_view`) filtra el historial solo por la PK del objeto.
       Peor: si el objeto no aparece en `get_queryset()` —que es exactamente lo
       que pasa cuando es de OTRA empresa— la librería cae a reconstruirlo desde
       el historial, y el chequeo de permisos que viene después es por modelo, no
       por fila. O sea que un admin de empresa que escribiera la URL a mano vería
       el remito ajeno completo. Acá el historial se vacía si el objeto no es
       suyo, y con las dos consultas en falso la vista termina en 404.
    2. El detalle (`history_form_view`) busca la versión directo en la tabla del
       historial, sin filtro de empresa: mismo agujero, misma solución.
    3. Ese mismo detalle acepta POST y REVIERTE el objeto a la versión que se
       está mirando. `SIMPLE_HISTORY_REVERT_DISABLED` solo esconde el botón en el
       template; el POST sigue respondiendo. Acá se corta de verdad: el historial
       es un libro de registro, se consulta y no se deshace.

    El superadmin de Friese no necesita excepción: para él `get_queryset()`
    devuelve todo, así que las tres comprobaciones le dan verdadero solas.
    """

    # Los títulos de las dos pantallas los arma la librería en inglés y no trae
    # traducción al español (ver la nota en templates/simple_history/).
    def history_view_title(self, request, obj):
        return f"Historial de cambios: {obj}"

    def history_form_view_title(self, request, obj):
        return f"Cómo estaba: {obj}"

    def _is_within_scope(self, request, object_id):
        """¿El objeto de esa PK es visible para este usuario?"""
        pk_name = self.model._meta.pk.attname
        return self.get_queryset(request).filter(**{pk_name: object_id}).exists()

    def get_history_queryset(self, request, history_manager, pk_name, object_id):
        queryset = super().get_history_queryset(
            request, history_manager, pk_name, object_id
        )
        if self._is_within_scope(request, object_id):
            return queryset
        return queryset.none()

    def history_form_view(self, request, object_id, version_id, extra_context=None):
        if not self._is_within_scope(request, object_id):
            raise Http404("No existe ese registro.")
        if request.method == "POST":
            # Revertir a una versión vieja. No se ofrece a nadie, ni al superadmin.
            raise PermissionDenied(
                "El historial es de solo lectura: no se puede revertir un registro "
                "a una versión anterior."
            )
        return super().history_form_view(
            request, object_id, version_id, extra_context=extra_context
        )
