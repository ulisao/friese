"""Suma los permisos de tickets al grupo "Admin de empresa" que YA existe.

`users/groups.py` carga los permisos del grupo UNA sola vez, cuando lo crea (a
propósito: así un ajuste manual del superadmin no se pisa en el próximo alta de
empresa). O sea que en una base donde el grupo ya está creado —la de producción—
agregar los permisos a esa lista no alcanza: hay que agregárselos al grupo.

Es aditivo: no toca ningún otro permiso del grupo.
"""

from django.db import migrations

GRUPO = "Admin de empresa"
PERMISOS = ("view_supportticket", "add_supportticket", "change_supportticket")


def _permisos(apps):
    # Los Permission de un modelo nuevo los crea un signal `post_migrate`, o sea
    # DESPUÉS de esta migración: acá se adelantan para poder engancharlos al grupo
    # en la misma corrida. Es idempotente (get_or_create adentro de Django).
    from django.apps import apps as registro_real
    from django.contrib.auth.management import create_permissions

    create_permissions(registro_real.get_app_config("support"), apps=apps, verbosity=0)
    Permission = apps.get_model("auth", "Permission")
    return Permission.objects.filter(
        content_type__app_label="support", codename__in=PERMISOS
    )


def agregar(apps, schema_editor):
    Group = apps.get_model("auth", "Group")
    grupo = Group.objects.filter(name=GRUPO).first()
    if grupo is None:
        # Base nueva: el grupo todavía no existe y lo va a crear
        # `ensure_company_admin_group()` con estos permisos ya en su lista.
        return
    grupo.permissions.add(*_permisos(apps))


def quitar(apps, schema_editor):
    Group = apps.get_model("auth", "Group")
    grupo = Group.objects.filter(name=GRUPO).first()
    if grupo is not None:
        grupo.permissions.remove(*_permisos(apps))


class Migration(migrations.Migration):

    dependencies = [
        ('support', '0001_initial'),
        ('auth', '__first__'),
        ('contenttypes', '__first__'),
    ]

    operations = [
        migrations.RunPython(agregar, quitar),
    ]
