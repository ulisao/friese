from django.apps import AppConfig


class ShipmentsConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'shipments'
    # Nombre de la sección en el panel (tarea 7.3).
    verbose_name = 'Remitos'

    def ready(self):
        # Registra los signals del despacho (trial, UsageLog, email al receptor).
        from . import signals  # noqa: F401
