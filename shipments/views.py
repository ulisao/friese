import uuid
from datetime import timedelta

from django.db import transaction
from django.db.models import Prefetch
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import generics, mixins, status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError
from rest_framework.parsers import FormParser, MultiPartParser
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import Evidence, Shipment, ShipmentItem
from .serializers import (
    DisputeSerializer,
    EvidenceSerializer,
    EvidenceUploadSerializer,
    PublicEvidenceSerializer,
    PublicShipmentSerializer,
    ReceptionEvidenceUploadSerializer,
    ShipmentItemSerializer,
    ShipmentSerializer,
)
from .storage import upload_evidence_file

# Ventana de respuesta del receptor: response_deadline = link_opened_at + 48 horas
# (docs/desarrollo.md sección 6). Valor fijo del spec.
RESPONSE_WINDOW = timedelta(hours=48)


def resolve_shipment_item(shipment, item_id):
    """Traduce el id de ítem del payload a un ShipmentItem de ESE remito.

    La foto puede documentar un producto concreto del remito o el remito completo
    (item_id ausente o null). Un id que no sea de este remito se rechaza con el mismo
    mensaje que uno inexistente, así el endpoint público no sirve para averiguar qué
    ids de ítem existen en otros remitos.
    """
    if item_id is None:
        return None

    item = shipment.items.filter(pk=item_id).first()
    if item is None:
        raise ValidationError(
            {"shipment_item": "El ítem no pertenece a este remito."}
        )
    return item


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

        `shipment_item` es opcional: si viene, la foto queda atada a ese producto del
        remito; si no, documenta el remito completo. Se pueden subir N fotos por ítem.
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
        item = resolve_shipment_item(
            shipment, payload.validated_data.get("shipment_item")
        )

        # Primero R2: si la subida falla (502), no queda un Evidence apuntando a un
        # archivo inexistente ni se suma una foto al UsageLog.
        file_url = upload_evidence_file(
            payload.validated_data["file"], shipment, evidence_type
        )
        evidence = Evidence.objects.create(
            shipment=shipment,
            shipment_item=item,
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


def public_shipment_queryset():
    """Queryset base del flujo público del receptor (tareas 3.1 / 3.2).

    Excluye los remitos sin public_token (los que están en draft): el token se genera
    recién al despachar, así que no hay forma de alcanzarlos por una URL pública.
    Trae anidado todo lo que devuelve PublicShipmentSerializer, para no hacer una
    query por ítem ni por foto.
    """
    return (
        Shipment.objects.filter(public_token__isnull=False)
        .select_related("company")
        .prefetch_related(
            "items__product",
            # Ordenadas por el timestamp del servidor: el receptor las ve en el
            # orden en que el operador las sacó.
            Prefetch("evidence", queryset=Evidence.objects.order_by("uploaded_at")),
        )
    )


class PublicShipmentView(generics.RetrieveAPIView):
    """GET /api/public/shipment/{token}/ — el remito visto por el receptor (sección 5).

    SIN autenticación: la única credencial es el public_token del link, que se genera
    recién al despachar (sección 6). Por eso el queryset excluye los remitos sin token
    (los que están en draft): no hay forma de llegar a uno de ellos por esta URL.

    authentication_classes vacío a propósito: la config global usa JWT y, si el
    navegador del receptor mandara un Authorization inválido, la request moriría en un
    401 antes de llegar acá. Este endpoint es público y no mira credenciales.
    """

    serializer_class = PublicShipmentSerializer
    permission_classes = [AllowAny]
    authentication_classes = []
    lookup_field = "public_token"
    lookup_url_kwarg = "token"

    def get_queryset(self):
        return public_shipment_queryset()

    def retrieve(self, request, *args, **kwargs):
        shipment = self.get_object()
        self._register_first_open(shipment)
        return Response(self.get_serializer(shipment).data)

    def _register_first_open(self, shipment):
        """Sella link_opened_at en la PRIMERA apertura y calcula response_deadline.

        Regla de la sección 6: link_opened_at se registra una sola vez; aperturas
        posteriores no lo tocan. La condición link_opened_at__isnull=True viaja dentro
        del propio UPDATE, así que si el receptor abre el link dos veces en paralelo
        solo una de las dos escribe (la otra actualiza 0 filas y relee el valor ya
        guardado). Se usa update() y no save() a propósito: no dispara los signals de
        Shipment, que son los del despacho.
        """
        if shipment.link_opened_at is not None:
            return

        opened_at = timezone.now()
        deadline = opened_at + RESPONSE_WINDOW
        updated = Shipment.objects.filter(
            pk=shipment.pk, link_opened_at__isnull=True
        ).update(link_opened_at=opened_at, response_deadline=deadline)

        if updated:
            # Se refleja en la instancia que se está por serializar, sin releer la DB.
            shipment.link_opened_at = opened_at
            shipment.response_deadline = deadline
        else:
            # Otra apertura simultánea ganó: se devuelve la marca que quedó guardada.
            shipment.refresh_from_db(
                fields=["link_opened_at", "response_deadline"]
            )


class PublicShipmentResponseView(APIView):
    """Base de la respuesta del receptor: aceptar o disputar (sección 5, tarea 3.2).

    SIN autenticación, igual que PublicShipmentView: la única credencial es el
    public_token del link. authentication_classes vacío para que un Authorization
    inválido del navegador no convierta la request en un 401.
    """

    permission_classes = [AllowAny]
    authentication_classes = []

    def get_shipment(self, token):
        return get_object_or_404(public_shipment_queryset(), public_token=token)

    def assert_can_respond(self, shipment):
        """Regla de la sección 6: solo se responde un remito despachado y en ventana.

        - Estado: `dispatched` es el único estado que admite respuesta. En `accepted`,
          `disputed` o `closed` el remito ya fue respondido (por el receptor o por el
          cierre automático de la 3.3) y la respuesta llegó tarde.
        - Ventana: response_deadline = link_opened_at + 48hs, sellado en la primera
          apertura del link (tarea 3.1). Si todavía es null, el link nunca se abrió y
          la ventana ni siquiera empezó a correr, así que no puede estar vencida: se
          deja responder.
        """
        if shipment.status != Shipment.DISPATCHED:
            raise ValidationError(
                "Este remito ya no admite respuesta: está en estado "
                f"'{shipment.status}'. Solo se puede aceptar o disputar un remito "
                "en estado 'dispatched'."
            )

        deadline = shipment.response_deadline
        if deadline is not None and timezone.now() > deadline:
            raise ValidationError(
                "La ventana de respuesta de 48 horas venció el "
                f"{timezone.localtime(deadline).strftime('%d/%m/%Y %H:%M')}. "
                "El remito ya no admite respuesta."
            )

    def close_response(self, shipment, new_status, dispute_reason=""):
        """Pasa el remito de dispatched al estado de respuesta, una sola vez.

        La condición `status=dispatched` viaja dentro del propio UPDATE: si dos
        respuestas entran en paralelo (aceptar y disputar, o dos clicks), solo una
        escribe y la otra actualiza 0 filas y termina en 400. Se usa update() y no
        save() a propósito, igual que en la apertura del link: los signals de Shipment
        son los del despacho y no tienen nada que hacer acá.
        """
        updated = Shipment.objects.filter(
            pk=shipment.pk, status=Shipment.DISPATCHED
        ).update(status=new_status, dispute_reason=dispute_reason)

        if not updated:
            # Perdió la carrera: otra respuesta ya movió el remito.
            shipment.refresh_from_db(fields=["status"])
            raise ValidationError(
                "Este remito ya no admite respuesta: está en estado "
                f"'{shipment.status}'."
            )

        # Se refleja en la instancia que se está por serializar, sin releer la DB.
        shipment.status = new_status
        shipment.dispute_reason = dispute_reason


class PublicShipmentAcceptView(PublicShipmentResponseView):
    """POST /api/public/shipment/{token}/accept/ — el receptor da conformidad."""

    def post(self, request, token):
        shipment = self.get_shipment(token)
        self.assert_can_respond(shipment)
        self.close_response(shipment, Shipment.ACCEPTED)
        return Response(PublicShipmentSerializer(shipment).data)


class PublicReceptionEvidenceView(PublicShipmentResponseView):
    """POST /api/public/shipment/{token}/evidence/ — foto de recepción del receptor.

    Mismo patrón que el operador en la tarea 2.8: el receptor saca las fotos de a una
    y recién después confirma la queja, así ve enseguida si una subida falló y puede
    reintentar esa sola foto. La ventana es la misma que para responder (sección 6:
    la evidencia de recepción se sube dentro de la ventana de respuesta), por eso
    reutiliza assert_can_respond().

    uploaded_by queda en null: el receptor no tiene usuario. `shipment_item` es
    opcional y ata la foto a un producto concreto del remito.
    """

    parser_classes = [MultiPartParser, FormParser]

    def post(self, request, token):
        shipment = self.get_shipment(token)
        self.assert_can_respond(shipment)

        payload = ReceptionEvidenceUploadSerializer(data=request.data)
        payload.is_valid(raise_exception=True)
        item = resolve_shipment_item(
            shipment, payload.validated_data.get("shipment_item")
        )

        file_url = upload_evidence_file(
            payload.validated_data["file"], shipment, Evidence.RECEPTION
        )
        evidence = Evidence.objects.create(
            shipment=shipment,
            shipment_item=item,
            type=Evidence.RECEPTION,
            uploaded_by=None,
            file_url=file_url,
        )
        return Response(
            PublicEvidenceSerializer(evidence).data, status=status.HTTP_201_CREATED
        )


class PublicShipmentDisputeView(PublicShipmentResponseView):
    """POST /api/public/shipment/{token}/dispute/ — el receptor confirma la queja.

    Las fotos ya se subieron por el endpoint de evidencia de recepción; acá solo se
    cierra la queja. Se exige al menos una foto de recepción, porque la sección 5
    define el endpoint como "registra queja con foto". `dispute_reason` es un texto
    opcional que explica el reclamo.
    """

    def post(self, request, token):
        shipment = self.get_shipment(token)
        self.assert_can_respond(shipment)

        payload = DisputeSerializer(data=request.data)
        payload.is_valid(raise_exception=True)
        reason = payload.validated_data.get("dispute_reason", "")

        if not any(e.type == Evidence.RECEPTION for e in shipment.evidence.all()):
            raise ValidationError(
                "Para registrar la queja hace falta al menos una foto de la carga "
                "recibida. Sacá la foto y volvé a confirmar."
            )

        with transaction.atomic():
            self.close_response(shipment, Shipment.DISPUTED, dispute_reason=reason)

        return Response(PublicShipmentSerializer(shipment).data)
