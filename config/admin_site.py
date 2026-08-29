"""Índice del Django Admin con las métricas del mes (tarea 10.2).

El admin de una empresa entra a su panel y ve de un vistazo cómo viene su mes
—remitos despachados, cuántos aceptados / en disputa / pendientes y cuántas fotos
de evidencia— antes de la lista de secciones de siempre.

El aislamiento multi-tenant es el mismo criterio de la tarea 4.1: el alcance NO
se lee del request salvo que quien mire sea el superadmin de Friese. Un admin de
empresa ve los números de su empresa y de ninguna otra, escriba lo que escriba en
la URL.
"""

from django.conf import settings
from django.contrib import admin

from companies.models import Company
from shipments.dashboard import metricas_del_mes


class FrieseAdminSite(admin.AdminSite):
    """AdminSite nativo + el resumen del mes arriba del índice."""

    index_template = "admin/friese_index.html"

    def each_context(self, request):
        """Contexto de TODAS las pantallas del panel, login incluido.

        Acá viajan las tres cosas que el pie necesita (tareas 7.5 y 7.7): a quién
        escribirle y los dos documentos legales. Van por `each_context` y no por la
        vista del índice porque el pie se dibuja en todas las pantallas, y es
        justamente en las que uno se pierde donde tiene que estar el contacto.
        """
        contexto = super().each_context(request)
        base = settings.FRONTEND_PUBLIC_URL.rstrip("/")
        contexto.update(
            support_email=settings.SUPPORT_CONTACT_EMAIL,
            support_whatsapp_url=settings.SUPPORT_WHATSAPP_URL,
            terminos_url=f"{base}/terminos",
            privacidad_url=f"{base}/privacidad",
        )
        return contexto

    def index(self, request, extra_context=None):
        extra_context = {
            **(extra_context or {}),
            "friese_dashboard": self.resumen_del_mes(request),
        }
        return super().index(request, extra_context=extra_context)

    def resumen_del_mes(self, request):
        """Contexto del resumen, o None si no hay nada que mostrarle a este usuario.

        El superadmin de Friese ve el consolidado de todas las empresas y puede
        acotarlo a una con el desplegable (`?empresa=<id>`). Cualquier otro usuario
        del panel queda atado a su propia empresa; si no tiene ninguna asignada no
        pertenece a ningún tenant y no le corresponde ningún número (mismo default
        seguro que `CompanyScopedAdminMixin`).
        """
        empresas = None
        if request.user.is_superuser:
            empresas = Company.objects.order_by("name")
            empresa = self._empresa_pedida(request)
        else:
            empresa = request.user.company
            if empresa is None:
                return None

        metricas = metricas_del_mes(company_id=empresa.pk if empresa else None)
        metricas["empresa"] = empresa
        metricas["empresa_id"] = empresa.pk if empresa else None
        metricas["empresas"] = empresas
        return metricas

    @staticmethod
    def _empresa_pedida(request):
        """La empresa del desplegable del superadmin, o None = todas."""
        pedida = request.GET.get("empresa")
        if not pedida or not pedida.isdigit():
            return None
        return Company.objects.filter(pk=int(pedida)).first()
