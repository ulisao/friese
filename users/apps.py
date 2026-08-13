from django.apps import AppConfig


class UsersConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'users'
    # Nombre de la sección en el panel (tarea 7.3).
    verbose_name = 'Usuarios y accesos'

    def ready(self):
        # La sección de tokens JWT es de simplejwt y llega al panel en inglés;
        # acá se le ponen los nombres en castellano (ver users/token_blacklist.py).
        from .token_blacklist import traducir_seccion_de_tokens

        traducir_seccion_de_tokens()
