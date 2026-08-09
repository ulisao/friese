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
        (ADMIN, "Admin"),
        (OPERATOR, "Operator"),
    ]

    # Nullable: el superadmin de Friese no pertenece a ninguna empresa.
    company = models.ForeignKey(
        "companies.Company",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="users",
    )
    role = models.CharField(max_length=20, choices=ROLE_CHOICES, blank=True)

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
    )
    token = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    is_used = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField()

    def __str__(self):
        return f"Invite {self.token} ({self.company})"
