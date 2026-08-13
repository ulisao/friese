from django.urls import path

from .auth_views import CookieTokenObtainPairView, CookieTokenRefreshView, LogoutView
from .password_reset import PasswordResetConfirmView, PasswordResetRequestView
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
    # Recuperación de contraseña (tarea 7.4). Los dos endpoints son públicos y
    # sirven igual al operador y al admin de empresa; ver users/password_reset.py.
    path(
        "password-reset/",
        PasswordResetRequestView.as_view(),
        name="password_reset_request",
    ),
    path(
        "password-reset/confirm/",
        PasswordResetConfirmView.as_view(),
        name="password_reset_confirm",
    ),
]
