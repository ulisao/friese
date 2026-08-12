"""Login / refresh / logout con el refresh token en una cookie httpOnly (tarea 6.7).

Qué cambia respecto de las vistas nativas de simplejwt:

- el refresh token DEJA de viajar en el cuerpo de la respuesta: va en una cookie
  `httpOnly` + `Secure` + `SameSite=Lax`, o sea fuera del alcance de JavaScript.
  Ante un XSS ya no se puede exfiltrar y usar desde otra máquina durante los 75
  días que vive el refresh;
- el access token no cambia: sigue viviendo solo en memoria del frontend y sigue
  viajando en el header `Authorization: Bearer`;
- se agrega logout, que blacklistea el refresh y borra la cookie.

Lo que NO cambia (sección 4 del spec): los tiempos de vida (45 min / 75 días), la
rotación, la blacklist y la revocación manual desde el Django Admin.
"""

from django.conf import settings
from rest_framework import status
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.exceptions import InvalidToken, TokenError
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView


def set_refresh_cookie(response, token):
    """Guarda el refresh token en la cookie httpOnly."""
    response.set_cookie(
        settings.REFRESH_COOKIE_NAME,
        token,
        max_age=int(settings.SIMPLE_JWT["REFRESH_TOKEN_LIFETIME"].total_seconds()),
        httponly=True,
        # En desarrollo el frontend corre sobre http://localhost, donde una cookie
        # Secure no se guarda: quedaría imposible probar el flujo localmente.
        secure=settings.IS_PRODUCTION,
        samesite="Lax",
        path=settings.REFRESH_COOKIE_PATH,
    )
    return response


def delete_refresh_cookie(response):
    response.delete_cookie(
        settings.REFRESH_COOKIE_NAME,
        path=settings.REFRESH_COOKIE_PATH,
        samesite="Lax",
    )
    return response


class CookieTokenObtainPairView(TokenObtainPairView):
    """POST /api/auth/login/ — devuelve SOLO el access; el refresh va en la cookie."""

    def post(self, request, *args, **kwargs):
        response = super().post(request, *args, **kwargs)
        refresh = response.data.pop("refresh", None)
        if refresh:
            set_refresh_cookie(response, refresh)
        return response


class CookieTokenRefreshView(TokenRefreshView):
    """POST /api/auth/refresh/ — toma el refresh de la cookie, no del cuerpo.

    El cliente no manda nada: el navegador adjunta la cookie solo. La respuesta
    trae únicamente el access nuevo, y el refresh rotado vuelve a la cookie (con
    ROTATE_REFRESH_TOKENS + BLACKLIST_AFTER_ROTATION, el anterior queda muerto).
    """

    def post(self, request, *args, **kwargs):
        token = request.COOKIES.get(settings.REFRESH_COOKIE_NAME)
        if not token:
            return Response(
                {"detail": "No hay sesión abierta en este dispositivo."},
                status=status.HTTP_401_UNAUTHORIZED,
            )

        # Se usa el serializer de simplejwt tal cual —con su validación, su
        # rotación y su blacklist—, solo que el token sale de la cookie en vez
        # del cuerpo de la request.
        serializer = self.get_serializer(data={"refresh": token})
        try:
            serializer.is_valid(raise_exception=True)
        except (TokenError, InvalidToken):
            # Refresh vencido o ya blacklisteado: además de responder 401, se borra
            # la cookie muerta para que el navegador no la siga mandando.
            return delete_refresh_cookie(
                Response(
                    {"detail": "La sesión expiró. Entrá de nuevo."},
                    status=status.HTTP_401_UNAUTHORIZED,
                )
            )

        datos = serializer.validated_data
        response = Response({"access": datos["access"]})
        # Con ROTATE_REFRESH_TOKENS el serializer devuelve un refresh nuevo: va a
        # la cookie, nunca al cuerpo.
        if datos.get("refresh"):
            set_refresh_cookie(response, datos["refresh"])
        return response


class LogoutView(APIView):
    """POST /api/auth/logout/ — cierra la sesión de ESTE dispositivo.

    Blacklistea el refresh de la cookie (así no sirve más aunque alguien lo tenga)
    y borra la cookie. Responde 205 igual si no había cookie o si el token ya
    estaba muerto: desde el punto de vista del usuario, la sesión quedó cerrada.
    """

    permission_classes = [AllowAny]

    def post(self, request):
        token = request.COOKIES.get(settings.REFRESH_COOKIE_NAME)
        if token:
            try:
                RefreshToken(token).blacklist()
            except TokenError:
                pass
        return delete_refresh_cookie(Response(status=status.HTTP_205_RESET_CONTENT))
