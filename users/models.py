import uuid

from django.contrib.auth.models import AbstractUser
from django.db import models
from simple_history.models import HistoricalRecords


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

    # Historial de cambios (tarea 8.2): a quién le cambiaron la empresa, el rol, el
    # `is_active` o los permisos, quién se lo cambió y cuándo. Es lo que permite
    # explicar después por qué un remito quedó firmado por tal operador.
    #
    # `password` queda EXCLUIDO a propósito: el hash no aporta nada a la auditoría y
    # copiarlo dejaría todas las contraseñas viejas de todos los usuarios en una
    # segunda tabla (y en cada dump del backup). El HECHO del cambio igual queda
    # registrado —simple_history escribe una fila por cada save—, con su fecha y su
    # autor; lo único que no se guarda es el hash anterior. Una fila del historial
    # sin ningún campo en la columna "Changes" es, casi siempre, un cambio de
    # contraseña.
    history = HistoricalRecords(
        excluded_fields=["password"],
        verbose_name="historial de usuario",
        verbose_name_plural="historial de usuarios",
    )

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
