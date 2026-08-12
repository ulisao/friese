from django.urls import path

from .auth_views import CookieTokenObtainPairView, CookieTokenRefreshView, LogoutView
from .views import RegisterOperatorView

# Endpoints de autenticación (ver docs/desarrollo.md sección 5).
# login/refresh son subclases de las vistas de simplejwt que mueven el refresh
# token a una cookie httpOnly (tarea 6.7): la rotación + blacklist las sigue
# aplicando la config SIMPLE_JWT (ROTATE_REFRESH_TOKENS / BLACKLIST_AFTER_ROTATION),
# que no cambió.
urlpatterns = [
    path("login/", CookieTokenObtainPairView.as_view(), name="login"),
    path("refresh/", CookieTokenRefreshView.as_view(), name="token_refresh"),
    path("logout/", LogoutView.as_view(), name="logout"),
    path("register-operator/", RegisterOperatorView.as_view(), name="register_operator"),
]
