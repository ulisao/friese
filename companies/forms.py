"""Formularios del admin de companies."""

from django import forms
from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import (
    password_validators_help_text_html,
    validate_password,
)
from django.core.exceptions import ValidationError

from users.groups import ensure_company_admin_group

from .models import Company

User = get_user_model()


class CompanyWithFirstAdminForm(forms.ModelForm):
    """Alta de una empresa nueva junto con su primer admin, en un solo paso.

    Una empresa sin ningún usuario no puede hacer nada, así que el alta pide los
    datos del primer admin en la misma pantalla. Se usa SOLO en el add de
    `CompanyAdmin`; la edición de una empresa existente usa el form normal.
    """

    admin_username = forms.CharField(
        label="Usuario",
        max_length=150,
        help_text="Login individual del admin de la empresa. Nunca compartido.",
    )
    admin_email = forms.EmailField(label="Email", required=False)
    admin_password = forms.CharField(
        label="Contraseña",
        widget=forms.PasswordInput,
        help_text=password_validators_help_text_html(),
    )
    admin_password_confirm = forms.CharField(
        label="Repetir contraseña",
        widget=forms.PasswordInput,
    )

    class Meta:
        model = Company
        fields = (
            "name",
            "email",
            "phone",
            "plan",
            "is_active",
            "trial_shipments_remaining",
        )

    def clean_admin_username(self):
        username = self.cleaned_data["admin_username"]
        if User.objects.filter(username=username).exists():
            raise ValidationError("Ya existe un usuario con ese nombre.")
        return username

    def clean(self):
        cleaned_data = super().clean()
        password = cleaned_data.get("admin_password")
        confirm = cleaned_data.get("admin_password_confirm")
        if password and confirm and password != confirm:
            self.add_error("admin_password_confirm", "Las dos contraseñas no coinciden.")
            return cleaned_data
        if password:
            # Mismos validadores que el resto del proyecto (settings
            # AUTH_PASSWORD_VALIDATORS); el usuario tentativo se pasa para que el
            # validador de similitud con los datos personales pueda actuar.
            tentative_user = User(
                username=cleaned_data.get("admin_username") or "",
                email=cleaned_data.get("admin_email") or "",
            )
            try:
                validate_password(password, tentative_user)
            except ValidationError as exc:
                self.add_error("admin_password", exc)
        return cleaned_data

    def create_first_admin(self, company):
        """Crea el primer admin de la empresa ya guardada y lo devuelve.

        `create_user` hashea la contraseña. `is_staff` + el grupo "Admin de
        empresa" son los que le dan acceso real al panel; el aislamiento por
        empresa lo aplica `CompanyScopedAdminMixin` (tarea 4.1).
        """
        user = User.objects.create_user(
            username=self.cleaned_data["admin_username"],
            email=self.cleaned_data["admin_email"],
            password=self.cleaned_data["admin_password"],
            company=company,
            role=User.ADMIN,
            is_staff=True,
        )
        user.groups.add(ensure_company_admin_group())
        return user
