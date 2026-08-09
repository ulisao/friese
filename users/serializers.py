from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password
from django.utils import timezone
from rest_framework import serializers

from .models import OperatorInvite

User = get_user_model()


class RegisterOperatorSerializer(serializers.Serializer):
    """Alta inicial de operador vía token de OperatorInvite (ver sección 4).

    Recibe el token del invite + credenciales, valida que el invite exista, no
    esté usado y no haya expirado, crea el User en la company del invite y marca
    el invite como usado.
    """

    token = serializers.UUIDField()
    username = serializers.CharField(max_length=150)
    password = serializers.CharField(write_only=True, style={"input_type": "password"})

    def validate_token(self, value):
        try:
            invite = OperatorInvite.objects.get(token=value)
        except OperatorInvite.DoesNotExist:
            raise serializers.ValidationError("Invitación inválida.")

        if invite.is_used:
            raise serializers.ValidationError("La invitación ya fue utilizada.")
        if invite.expires_at <= timezone.now():
            raise serializers.ValidationError("La invitación expiró.")

        self._invite = invite
        return value

    def validate_username(self, value):
        if User.objects.filter(username=value).exists():
            raise serializers.ValidationError("El nombre de usuario ya está en uso.")
        return value

    def validate_password(self, value):
        validate_password(value)
        return value

    def create(self, validated_data):
        invite = self._invite
        user = User.objects.create_user(
            username=validated_data["username"],
            password=validated_data["password"],
            company=invite.company,
            role=User.OPERATOR,
        )
        invite.is_used = True
        invite.save(update_fields=["is_used"])
        return user
