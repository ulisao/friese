import uuid

from django.db import transaction
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import mixins, status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError
from rest_framework.parsers import FormParser, MultiPartParser
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from .models import Evidence, Shipment, ShipmentItem
from .serializers import (
    EvidenceSerializer,
    EvidenceUploadSerializer,
    ShipmentItemSerializer,
    ShipmentSerializer,
)
from .storage import upload_evidence_file


class ShipmentViewSet(
    mixins.CreateModelMixin,
    mixins.ListModelMixin,
    mixins.RetrieveModelMixin,
    viewsets.GenericViewSet,
):
    """Remitos del operador: list / create / detail (ver docs/desarrollo.md sección 5).

    Solo se exponen list, create y retrieve (sin update/delete: la edición del draft
    y el despacho son tareas posteriores 2.2/2.3). Todo se filtra por la company del
    usuario autenticado, de modo que un operador nunca ve remitos de otra empresa.
    """

    serializer_class = ShipmentSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        # Filtro de aislamiento multi-tenant (sección 2.2). Si el usuario no tiene
        # company (p. ej. el superadmin de Friese), company=None no matchea ningún
        # remito (Shipment.company es obligatorio) → queryset vacío.
        return (
            Shipment.objects.filter(company=self.request.user.company)
            # items y evidence van anidados en el serializer: sin prefetch la lista
            # haría dos queries por remito.
            .prefetch_related("items__product", "evidence")
            .order_by("-created_at")
        )

    def perform_create(self, serializer):
        user = self.request.user
        if user.company_id is None:
            raise ValidationError("El usuario no pertenece a ninguna empresa.")
        # company y operator salen del usuario autenticado, no del payload.
        # status=draft explícito (regla de negocio sección 6).
        serializer.save(
            company=user.company,
            operator=user,
            status=Shipment.DRAFT,
        )

    # El método NO puede llamarse dispatch(): APIView ya usa ese nombre para el
    # ruteo interno. url_path fija la URL pedida por el spec.
    @action(detail=True, methods=["patch"], url_path="dispatch", url_name="dispatch")
    def dispatch_shipment(self, request, pk=None):
        """PATCH /api/shipments/{id}/dispatch/ — despacha el remito (sección 5).

        Genera el public_token (solo acá, nunca antes — sección 6), pasa el remito a
        dispatched y sella dispatched_at. El descuento del trial, el UsageLog del mes
        y el email al receptor los dispara el signal de post_save (shipments/signals.py).
        """
        shipment = self.get_object()
        # Solo se despacha un draft: despachar dos veces duplicaría el consumo y
        # rompería la inmutabilidad del remito despachado (sección 6).
        if shipment.status != Shipment.DRAFT:
            raise ValidationError(
                "Solo se puede despachar un remito en estado 'draft'. "
                f"Este remito está en estado '{shipment.status}'."
            )

        shipment.status = Shipment.DISPATCHED
        shipment.dispatched_at = timezone.now()
        shipment.public_token = uuid.uuid4()
        # atomic: el save y los efectos del signal (trial + UsageLog) commitean juntos.
        with transaction.atomic():
            shipment.save(
                update_fields=["status", "dispatched_at", "public_token"]
            )

        return Response(self.get_serializer(shipment).data)

    @action(
        detail=True,
        methods=["post"],
        url_path="evidence",
        url_name="evidence",
        parser_classes=[MultiPartParser, FormParser],
        serializer_class=EvidenceUploadSerializer,
    )
    def upload_evidence(self, request, pk=None):
        """POST /api/shipments/{id}/evidence/ — sube la foto de despacho (sección 5).

        Regla de estado: la evidencia de despacho se sube en draft (antes de despachar)
        o en dispatched (después). accepted/disputed/closed ya cerraron la ventana y se
        rechazan. El draft se habilitó en la tarea 2.8: el operador saca las fotos desde
        el detalle del remito y el despacho recién se dispara cuando las fotos subieron
        bien, así que un remito nunca queda despachado (irreversible) sin su evidencia.

        El archivo va a Cloudflare R2 y en Evidence queda su URL. uploaded_at lo pone
        el servidor (auto_now_add), nunca el cliente: es la fuente de verdad del
        timestamp de la evidencia (sección 3).
        """
        shipment = self.get_object()
        if shipment.status not in (Shipment.DRAFT, Shipment.DISPATCHED):
            raise ValidationError(
                "Solo se puede subir evidencia de despacho mientras el remito está en "
                "estado 'draft' o 'dispatched'. Este remito está en estado "
                f"'{shipment.status}'."
            )

        payload = EvidenceUploadSerializer(data=request.data)
        payload.is_valid(raise_exception=True)
        evidence_type = payload.validated_data["type"]

        # Primero R2: si la subida falla (502), no queda un Evidence apuntando a un
        # archivo inexistente ni se suma una foto al UsageLog.
        file_url = upload_evidence_file(
            payload.validated_data["file"], shipment, evidence_type
        )
        evidence = Evidence.objects.create(
            shipment=shipment,
            type=evidence_type,
            uploaded_by=request.user,
            file_url=file_url,
        )
        return Response(
            EvidenceSerializer(evidence).data, status=status.HTTP_201_CREATED
        )


class ShipmentItemViewSet(viewsets.ModelViewSet):
    """Ítems de un remito, anidados bajo /api/shipments/{shipment_pk}/items/ (tarea 2.2).

    CRUD completo (list/create/retrieve/update/partial_update/destroy). Regla de negocio
    (sección 6): un remito en draft puede editarse; una vez despachado es inmutable, así
    que cualquier escritura (crear/editar/borrar item) sobre un remito que no esté en
    draft se rechaza con 400 y un mensaje claro (nunca un 500). Todo se aísla por la
    company del usuario autenticado (sección 2.2): un remito ajeno da 404.
    """

    serializer_class = ShipmentItemSerializer
    permission_classes = [IsAuthenticated]

    def initial(self, request, *args, **kwargs):
        # super() corre auth + permisos primero (anónimo → 401 antes de tocar la DB).
        super().initial(request, *args, **kwargs)
        # Toda acción (incluido list) resuelve el remito padre y valida que sea de la
        # company del usuario: un remito ajeno o inexistente da 404 uniforme (sección 2.2).
        self.shipment = get_object_or_404(
            Shipment,
            pk=self.kwargs["shipment_pk"],
            company=request.user.company,
        )

    def get_queryset(self):
        return ShipmentItem.objects.filter(shipment=self.shipment)

    def _assert_draft(self, shipment):
        # Un remito despachado (o en cualquier estado != draft) es inmutable (sección 6).
        if shipment.status != Shipment.DRAFT:
            raise ValidationError(
                "Solo se pueden modificar los ítems de un remito en estado 'draft'. "
                f"Este remito está en estado '{shipment.status}'."
            )

    def perform_create(self, serializer):
        self._assert_draft(self.shipment)
        serializer.save(shipment=self.shipment)

    def perform_update(self, serializer):
        self._assert_draft(serializer.instance.shipment)
        serializer.save()

    def perform_destroy(self, instance):
        self._assert_draft(instance.shipment)
        instance.delete()
