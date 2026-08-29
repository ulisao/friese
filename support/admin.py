from django.contrib import admin
from django.db import transaction

from companies.admin_mixins import CompanyScopedHistoryAdmin

from .emails import build_ticket_admin_link, send_new_ticket_email
from .models import SupportTicket


@admin.register(SupportTicket)
class SupportTicketAdmin(CompanyScopedHistoryAdmin):
    """Tickets de soporte (tarea 9.1).

    Aislado por empresa con el mixin de la 4.1: el admin de una empresa ve y crea
    SOLO los tickets de su empresa; el superadmin de Friese los ve todos y es el
    único que mueve el estado.

    Para el admin de empresa, `company` y `created_by` no se eligen: se completan
    solos con su empresa y su usuario (`save_model`). Un desplegable ahí sería
    una pregunta con una sola respuesta posible — y en el caso de `company`, la
    manera de crear un ticket dentro de otra empresa.
    """

    # `company_lookup` queda en el default ("company"): el ticket apunta derecho
    # al tenant. Los lookups de FK son la red de seguridad por si algún día estos
    # campos se vuelven editables para el admin de empresa: hoy le llegan de solo
    # lectura, así que ni siquiera están en su formulario.
    company_fk_lookups = {"company": "pk", "created_by": "company"}

    list_display = ("id", "subject", "company", "created_by", "status", "created_at", "updated_at")
    list_filter = ("status", "company")
    search_fields = ("subject", "description", "company__name")
    autocomplete_fields = ("company",)
    readonly_fields = ("created_by", "created_at", "updated_at")

    # Lo decide Friese, no el cliente: quien abre el ticket no dictamina si está
    # resuelto (criterio de aceptación de la 9.1).
    friese_only_fields = ("status",)

    def get_readonly_fields(self, request, obj=None):
        readonly_fields = tuple(super().get_readonly_fields(request, obj))
        if request.user.is_superuser:
            return readonly_fields
        # `company` también: el ticket nace en la empresa de quien lo abre.
        return readonly_fields + self.friese_only_fields + ("company",)

    def get_fields(self, request, obj=None):
        if obj is None:
            # Alta: el admin de empresa solo escribe el pedido. Las fechas todavía
            # no existen y el estado arranca en "Abierto" por el default del modelo.
            if request.user.is_superuser:
                return ("company", "subject", "description", "status")
            return ("subject", "description")
        return (
            "company", "created_by", "subject", "description", "status",
            "created_at", "updated_at",
        )

    def has_add_permission(self, request):
        if not super().has_add_permission(request):
            return False
        # Un usuario del panel sin empresa y que no es el superadmin no pertenece
        # a ningún tenant: su ticket no tendría empresa a la cual pertenecer.
        return request.user.is_superuser or request.user.company_id is not None

    def save_model(self, request, obj, form, change):
        if not change:
            # Los dos campos llegan vacíos desde el formulario del admin de
            # empresa (los recibe de solo lectura). El autor se sella siempre con
            # quien está logueado: es el dato honesto y no hace falta preguntarlo.
            obj.created_by = request.user
            if obj.company_id is None:
                obj.company_id = request.user.company_id
        super().save_model(request, obj, form, change)

        if not change:
            # Aviso a Friese de que hay un ticket nuevo (tarea 9.2). Va acá y no en
            # un signal `post_save` porque el link del email apunta a la ficha del
            # ticket en ESTE panel, y el host sale del request (ver support/emails.py).
            # El alta por el admin es además el único camino por el que hoy nace un
            # ticket: no hay endpoint de API ni pantalla en el frontend (tarea 9.1).
            #
            # `on_commit`: si el alta se revierte, no sale un email avisando de un
            # ticket que no existe. Y `send_new_ticket_email()` no levanta
            # excepciones, así que una caída de Resend no rompe el alta ya guardada.
            link = build_ticket_admin_link(obj, request)
            transaction.on_commit(lambda: send_new_ticket_email(obj, link))
