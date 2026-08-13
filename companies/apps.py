from django.apps import AppConfig


class CompaniesConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'companies'
    # Nombre de la sección en el panel (tarea 7.3).
    verbose_name = 'Empresas'
