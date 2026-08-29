"""AppConfig del Django Admin (tarea 10.2).

Reemplaza a `django.contrib.admin` en INSTALLED_APPS para que `admin.site` sea el
`FrieseAdminSite` (el índice con las métricas del mes) en vez del AdminSite
nativo. Es el mecanismo que documenta Django para cambiar el sitio por defecto.

Este módulo se importa MUY temprano —al armar el registro de apps, antes de que
los modelos existan—, así que no puede importar nada del proyecto: por eso el
sitio se referencia por su ruta y vive en `config/admin_site.py`, que se importa
recién cuando `admin.site` se usa por primera vez.
"""

from django.contrib.admin.apps import AdminConfig


class FrieseAdminConfig(AdminConfig):
    default_site = "config.admin_site.FrieseAdminSite"
