from django.apps import AppConfig


class CatalogConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'catalog'
    # Nombre de la sección en el panel (tarea 7.3).
    verbose_name = 'Catálogo'
