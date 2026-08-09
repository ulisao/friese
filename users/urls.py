from django.urls import path
from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView

from .views import RegisterOperatorView

# Endpoints de autenticación (ver docs/desarrollo.md sección 5).
# login/refresh usan las vistas nativas de simplejwt; la rotación + blacklist del
# refresh la aplica la config SIMPLE_JWT (ROTATE_REFRESH_TOKENS / BLACKLIST_AFTER_ROTATION).
urlpatterns = [
    path("login/", TokenObtainPairView.as_view(), name="login"),
    path("refresh/", TokenRefreshView.as_view(), name="token_refresh"),
    path("register-operator/", RegisterOperatorView.as_view(), name="register_operator"),
]
