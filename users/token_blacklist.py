"""Traducción de la sección de tokens JWT en el panel (tarea 7.3).

Los modelos `OutstandingToken` / `BlacklistedToken` los trae simplejwt, y el admin
de la empresa los ve: la sección 4 pide que pueda revocar el refresh token de un
operador puntual (los admins scopeados están en `users/admin.py`).

simplejwt marca esos nombres para traducir y hasta trae un catálogo `es_AR`, pero
Django nunca lo carga: el catálogo vive en `rest_framework_simplejwt/locale` y la
app instalada es la de más adentro (`...simplejwt.token_blacklist`), que no tiene
`locale/` propio. Por eso al cliente le aparecían "Token Blacklist" y "Outstanding
Tokens" en inglés, en medio de un panel en castellano.

No se puede resolver subclaseando su AppConfig: los modelos de simplejwt se
declaran abstractos salvo que el string exacto `rest_framework_simplejwt.token_blacklist`
esté en INSTALLED_APPS, así que instalarlos por otra ruta los deja fuera del admin.
Queda entonces reescribir los nombres en `ready()`, que es lo que hace esto.
"""

from django.apps import apps


def traducir_seccion_de_tokens():
    """Pone en castellano el nombre de la sección de tokens y el de sus dos modelos.

    Se llama desde `UsersConfig.ready()`. Se toca ÚNICAMENTE `_meta.verbose_name`,
    no `_meta.original_attrs`: el autodetector de migraciones arma el estado del
    modelo a partir de `original_attrs`, así que dejándolo intacto sigue viendo los
    nombres originales y `makemigrations` no intenta escribir una migración adentro
    del paquete de simplejwt, que no es nuestro y no se puede versionar. Lo que
    cambia es solo la etiqueta que se dibuja en el panel.
    """
    apps.get_app_config("token_blacklist").verbose_name = "Sesiones de operadores"

    nombres = {
        # "Outstanding" = el refresh token sigue vigente; blacklistearlo es lo que
        # cierra la sesión de ese operador en su celular.
        "OutstandingToken": ("Sesión abierta", "Sesiones abiertas"),
        "BlacklistedToken": ("Sesión revocada", "Sesiones revocadas"),
    }
    for nombre_modelo, (singular, plural) in nombres.items():
        meta = apps.get_model("token_blacklist", nombre_modelo)._meta
        meta.verbose_name = singular
        meta.verbose_name_plural = plural
