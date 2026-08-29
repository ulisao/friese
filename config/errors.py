"""Páginas de error del backend con la marca de Friese (tarea 10.4).

Django trae dos vistas por defecto para 404 y 500 y las renderiza con templates
propios (`404.html` / `500.html`) apenas existan. Acá se reemplazan las VISTAS,
no solo los templates, por un motivo concreto: la vista de 500 de Django renderiza
el template **sin contexto y sin request** (así se protege de que un error del
servidor se convierta en un segundo error), así que un `{{ settings.X }}` o
cualquier context processor no llegan a la pantalla. Con estos handlers las dos
páginas reciben exactamente el mismo contexto y quedan iguales.

El contenido es deliberadamente austero: HTML propio con estilos embebidos y sin
un solo archivo estático (ver `templates/errores/base.html`). Una página de error
que depende de que algo más funcione no sirve como página de error.
"""

from django.conf import settings
from django.shortcuts import render


def _contexto():
    """Lo que las dos pantallas necesitan: a dónde volver y a quién escribirle."""
    return {
        "app_url": settings.FRONTEND_PUBLIC_URL.rstrip("/"),
        "support_email": settings.SUPPORT_CONTACT_EMAIL,
        "support_whatsapp_url": settings.SUPPORT_WHATSAPP_URL,
        "support_whatsapp": settings.SUPPORT_WHATSAPP_DISPLAY,
    }


def page_not_found(request, exception, template_name="404.html"):
    """404 — la URL no existe. Misma firma que `django.views.defaults`."""
    return render(request, template_name, _contexto(), status=404)


def server_error(request, template_name="500.html"):
    """500 — algo se rompió del lado del servidor."""
    return render(request, template_name, _contexto(), status=500)
