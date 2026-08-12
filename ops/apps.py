from django.apps import AppConfig


class OpsConfig(AppConfig):
    """Infraestructura del proyecto (backups). No tiene modelos ni endpoints."""

    default_auto_field = "django.db.models.BigAutoField"
    name = "ops"
    verbose_name = "Operaciones"
