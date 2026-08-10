"""Grupo de permisos con el que entra un admin de empresa al Django Admin.

`User.role='admin'` (docs/Desarrollo.md sección 3) dice QUIÉN es el admin de la
empresa, pero no le da acceso al panel: eso lo dan `is_staff` + los permisos
nativos de Django. Acá se define, en un único lugar, el set de permisos del admin
de empresa, para no tildarlos a mano en cada alta.

El aislamiento por empresa NO se hace con permisos, sino con
`CompanyScopedAdminMixin` (tarea 4.1): estos permisos dicen QUÉ modelos puede
manejar; el mixin lo acota a las filas de su propia empresa.
"""

from django.contrib.auth.models import Group, Permission
from django.db.models import Q

COMPANY_ADMIN_GROUP_NAME = "Admin de empresa"

# Permisos del grupo, como "app_label.codename".
COMPANY_ADMIN_PERMISSIONS = (
    # Su propia ficha de empresa (datos de contacto). El plan, el trial y
    # is_active los deja readonly CompanyAdmin: son de Friese.
    "companies.view_company",
    "companies.change_company",
    # Su consumo mensual y su tier (el admin de UsageLog es de solo lectura).
    "companies.view_usagelog",
    # Sus usuarios: dar de alta operadores y otros admins, editarlos y
    # desactivarlos. Sin delete: un operador con remitos no se borra
    # (Shipment.operator es PROTECT), se desactiva con is_active.
    "users.view_user",
    "users.add_user",
    "users.change_user",
    # Invitaciones de alta de operador (el QR de la sección 4).
    "users.view_operatorinvite",
    "users.add_operatorinvite",
    "users.change_operatorinvite",
    "users.delete_operatorinvite",
    # Catálogo de productos de la empresa.
    "catalog.view_product",
    "catalog.add_product",
    "catalog.change_product",
    "catalog.delete_product",
    # Remitos y evidencia: SOLO LECTURA. El remito lo crea y despacha el
    # operador desde su frontend, y despachado es inmutable (sección 6): lo que
    # Friese vende es evidencia que no se puede retocar después.
    "shipments.view_shipment",
    "shipments.view_shipmentitem",
    "shipments.view_evidence",
    # Revocar el refresh token de un operador puntual, p. ej. por un celular
    # perdido (sección 4). Los OutstandingToken son de solo lectura.
    "token_blacklist.view_outstandingtoken",
    "token_blacklist.view_blacklistedtoken",
    "token_blacklist.add_blacklistedtoken",
)


def ensure_company_admin_group():
    """Devuelve el grupo "Admin de empresa", creándolo la primera vez.

    Los permisos se cargan SOLO al crear el grupo: si después el superadmin de
    Friese lo ajusta a mano desde el admin, el próximo alta de empresa no le pisa
    esa decisión.
    """
    group, created = Group.objects.get_or_create(name=COMPANY_ADMIN_GROUP_NAME)
    if created:
        lookup = Q()
        for permission in COMPANY_ADMIN_PERMISSIONS:
            app_label, codename = permission.split(".")
            lookup |= Q(content_type__app_label=app_label, codename=codename)
        group.permissions.set(Permission.objects.filter(lookup))
    return group
