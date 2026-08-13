"""
URL configuration for config project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/5.1/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""
from django.conf import settings
from django.contrib import admin
from django.urls import include, path

# Branding del panel (tarea 7.3). Reemplaza el "Django administration" por defecto
# en el header, en el <title> de la pestaña y en el encabezado del índice. El
# aspecto visual va en templates/admin/base_site.html + static/admin/css/friese.css.
admin.site.site_header = "Panel Friese"
admin.site.site_title = "Panel Friese"
admin.site.index_title = "Administración"
# "Ver sitio" apuntaba a "/" del backend, que no sirve nada (la API vive bajo
# /api/). Se lo manda a la app del frontend, que es el sitio real del producto.
admin.site.site_url = settings.FRONTEND_PUBLIC_URL

urlpatterns = [
    path('admin/', admin.site.urls),
    path('api/auth/', include('users.urls')),
    path('api/', include('catalog.urls')),
    path('api/', include('shipments.urls')),
]
