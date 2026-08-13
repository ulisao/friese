"""Recuperación de contraseña por email (tarea 7.4).

Es el flujo estándar de "olvidé mi contraseña", en DOS pasos:

  1. POST /api/auth/password-reset/         {"identifier": usuario o email}
     Busca al usuario, le manda un link con un token de un solo uso y responde
     SIEMPRE lo mismo, exista o no (si contestara distinto, el endpoint serviría
     para averiguar qué usuarios existen).

  2. POST /api/auth/password-reset/confirm/ {"uid", "token", "password"}
     Valida el par uid + token y guarda la contraseña nueva.

Un solo flujo para los dos tipos de usuario, como pide la tarea: el operador
llega desde la app (frontend/src/pages/ForgotPasswordPage.jsx) y el admin de
empresa desde el link "¿Perdiste tu contraseña?" del login del panel, que
redirige a esa misma pantalla (config/urls.py, `admin_password_reset`). Lo único
que cambia entre uno y otro es la línea del email que dice dónde volver a entrar.

El token es el de Django (`default_token_generator`), sin modelo nuevo: se firma
con el hash de la contraseña actual y con `last_login`, así que se invalida solo
en cuanto la contraseña cambia (o sea, sirve UNA vez) y vence a las
`PASSWORD_RESET_TIMEOUT` (settings, 24hs por default).

Nada de la sección 4 del spec cambia: el login sigue siendo individual con
usuario + contraseña, y los tiempos, la rotación y la blacklist de los JWT
quedan como estaban. Lo que sí hace este flujo es cerrar las sesiones abiertas
del usuario al terminar (ver `_close_open_sessions`).
"""

import logging

from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password
from django.contrib.auth.tokens import default_token_generator
from django.db.models import Q
from django.utils.encoding import force_bytes, force_str
from django.utils.http import urlsafe_base64_decode, urlsafe_base64_encode
from rest_framework import serializers, status
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.token_blacklist.models import (
    BlacklistedToken,
    OutstandingToken,
)

from .emails import build_reset_link, send_password_reset_email
from .throttling import PASSWORD_RESET_THROTTLES

logger = logging.getLogger(__name__)

User = get_user_model()

# La misma respuesta para el usuario que existe y para el que no: desde afuera no
# se puede distinguir un caso del otro.
RESPUESTA_GENERICA = (
    "Si ese usuario existe y tiene un email cargado, ya le mandamos un link para "
    "elegir una contraseña nueva. Revisá tu casilla, incluido el correo no deseado."
)

LINK_INVALIDO = (
    "Este link no sirve más: venció o ya lo usaste. Pedí uno nuevo desde "
    "«¿Olvidaste tu contraseña?»."
)


def usuarios_para(identifier):
    """Usuarios que pueden recibir el link para el texto que se tipeó.

    Se acepta el usuario o el email en el mismo campo: el operador se acuerda de
    su usuario y el admin de su email, y preguntar cuál es cuál no le suma nada a
    nadie. Como el email NO es único en Django, un mismo email puede pertenecer a
    más de una cuenta; en ese caso se le manda un link a cada una y el email
    aclara de qué usuario es cada uno (igual que hace el flujo nativo de Django).

    Quedan afuera los inactivos (`is_active=False` es la baja del sistema), los
    que no tienen email cargado (no hay dónde mandarles nada) y los que no tienen
    una contraseña utilizable.
    """
    identifier = (identifier or "").strip()
    if not identifier:
        return []

    candidatos = (
        User.objects.filter(is_active=True)
        .filter(Q(username__iexact=identifier) | Q(email__iexact=identifier))
        .exclude(email="")
        .order_by("pk")
    )
    return [user for user in candidatos if user.has_usable_password()]


def _close_open_sessions(user):
    """Blacklistea los refresh tokens vigentes del usuario.

    Cambiar la contraseña tiene que cerrar las sesiones abiertas: si alguien se
    metió con la contraseña vieja, su refresh vive hasta 75 días (sección 4) y
    seguiría entrando aunque el dueño la cambie. Es el mismo mecanismo que usa el
    admin para revocar el token de un operador puntual, aplicado a todos los de
    este usuario.
    """
    for token in OutstandingToken.objects.filter(user=user):
        BlacklistedToken.objects.get_or_create(token=token)


class PasswordResetRequestSerializer(serializers.Serializer):
    """Paso 1: a quién hay que mandarle el link."""

    identifier = serializers.CharField(max_length=254)


class PasswordResetConfirmSerializer(serializers.Serializer):
    """Paso 2: el par uid + token del link, más la contraseña nueva."""

    uid = serializers.CharField()
    token = serializers.CharField()
    password = serializers.CharField(write_only=True, style={"input_type": "password"})

    def _usuario_del_uid(self, uid):
        try:
            pk = force_str(urlsafe_base64_decode(uid))
            return User.objects.get(pk=pk, is_active=True)
        except (TypeError, ValueError, OverflowError, User.DoesNotExist):
            return None

    def validate(self, attrs):
        # El uid y el token se validan juntos porque el token solo se puede
        # verificar contra un usuario concreto.
        user = self._usuario_del_uid(attrs["uid"])
        if user is None or not default_token_generator.check_token(user, attrs["token"]):
            raise serializers.ValidationError({"token": LINK_INVALIDO})

        # Con el usuario delante, los validators de Django también chequean que la
        # contraseña no se parezca a su nombre de usuario ni a su email.
        validate_password(attrs["password"], user)

        self.user = user
        return attrs

    def save(self):
        user = self.user
        user.set_password(self.validated_data["password"])
        user.save(update_fields=["password"])
        _close_open_sessions(user)
        return user


class PasswordResetRequestView(APIView):
    """POST /api/auth/password-reset/ — manda el link de recuperación."""

    permission_classes = [AllowAny]
    # Sin autenticación: el que olvidó la contraseña no tiene sesión. Se declara
    # explícito para que un access token viejo no cambie el cupo del throttle.
    authentication_classes = []
    throttle_classes = PASSWORD_RESET_THROTTLES

    def post(self, request):
        serializer = PasswordResetRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        identifier = serializer.validated_data["identifier"]

        usuarios = usuarios_para(identifier)
        if not usuarios:
            # Solo queda en el log del servidor: la respuesta es la misma de
            # siempre para no delatar qué usuarios existen.
            logger.info(
                "Recuperación de contraseña pedida para «%s»: no hay ningún "
                "usuario activo con email que coincida.",
                identifier,
            )

        # El panel del admin vive en el mismo host que esta API, así que su URL se
        # arma desde la request y no hace falta una variable de entorno nueva.
        admin_url = request.build_absolute_uri("/admin/")
        for user in usuarios:
            link = build_reset_link(
                urlsafe_base64_encode(force_bytes(user.pk)),
                default_token_generator.make_token(user),
            )
            send_password_reset_email(user, link, admin_url=admin_url)

        return Response({"detail": RESPUESTA_GENERICA})


class PasswordResetConfirmView(APIView):
    """POST /api/auth/password-reset/confirm/ — guarda la contraseña nueva."""

    permission_classes = [AllowAny]
    authentication_classes = []
    throttle_classes = PASSWORD_RESET_THROTTLES

    def post(self, request):
        serializer = PasswordResetConfirmSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = serializer.save()

        logger.info(
            "Contraseña cambiada por recuperación: usuario %s.", user.get_username()
        )
        return Response(
            {"detail": "Listo: tu contraseña quedó actualizada."},
            status=status.HTTP_200_OK,
        )
