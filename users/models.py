import uuid

from django.contrib.auth.models import AbstractUser
from django.db import models


class User(AbstractUser):
    """User extendido con company y role. Ver docs/desarrollo.md sección 3.

    `is_active` y el login individual (usuario + contraseña) vienen de AbstractUser.
    """

    ADMIN = "admin"
    OPERATOR = "operator"
    ROLE_CHOICES = [
        (ADMIN, "Admin de empresa"),
        (OPERATOR, "Operador"),
    ]

    # Nullable: el superadmin de Friese no pertenece a ninguna empresa.
    company = models.ForeignKey(
        "companies.Company",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="users",
        verbose_name="Empresa",
    )
    role = models.CharField("Rol", max_length=20, choices=ROLE_CHOICES, blank=True)

    class Meta(AbstractUser.Meta):
        verbose_name = "Usuario"
        verbose_name_plural = "Usuarios"

    def __str__(self):
        return self.get_username()


class OperatorInvite(models.Model):
    """Invitación de alta inicial de operador (QR). No es login recurrente.

    Ver docs/desarrollo.md secciones 3 y 4.
    """

    company = models.ForeignKey(
        "companies.Company",
        on_delete=models.CASCADE,
        related_name="operator_invites",
        verbose_name="Empresa",
    )
    token = models.UUIDField("Token", default=uuid.uuid4, unique=True, editable=False)
    is_used = models.BooleanField("Usada", default=False)
    created_at = models.DateTimeField("Fecha de creación", auto_now_add=True)
    expires_at = models.DateTimeField("Vence el")

    class Meta:
        verbose_name = "Invitación de operador"
        verbose_name_plural = "Invitaciones de operador"

    def __str__(self):
        return f"Invitación {self.token} ({self.company})"
