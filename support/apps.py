from django.apps import AppConfig


class SupportConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'support'
    # Nombre de la sección en el panel (mismo criterio que la 7.3).
    verbose_name = 'Soporte'
