from rest_framework import serializers

from .models import Evidence, Shipment, ShipmentItem


class ShipmentItemSerializer(serializers.ModelSerializer):
    """Ítem (producto + cantidad + notas) de un remito (ver sección 3).

    shipment NO se toma del payload: lo fija la vista a partir de la URL anidada
    (/api/shipments/{shipment_pk}/items/). El producto debe pertenecer a la misma
    empresa del usuario autenticado (aislamiento multi-tenant, sección 2.2).

    product_name/product_unit son de solo lectura y viajan para que el detalle del
    remito pueda mostrar "50 bolsas" sin pedir el catálogo aparte (GET /api/products/
    devuelve solo los activos, así que un producto dado de baja no se resolvería).
    """

    product_name = serializers.CharField(source="product.name", read_only=True)
    product_unit = serializers.CharField(source="product.unit", read_only=True)

    class Meta:
        model = ShipmentItem
        fields = [
            "id",
            "product",
            "product_name",
            "product_unit",
            "quantity",
            "notes",
        ]

    def validate_product(self, product):
        request = self.context.get("request")
        if request is not None and product.company_id != request.user.company_id:
            raise serializers.ValidationError(
                "El producto no pertenece a tu empresa."
            )
        return product


class EvidenceSerializer(serializers.ModelSerializer):
    """Foto de evidencia ya subida a R2 (ver sección 3). Solo lectura.

    Todos los campos los fija el servidor: file_url lo devuelve R2 tras la subida,
    uploaded_by es el usuario autenticado y uploaded_at es el timestamp del servidor
    (auto_now_add), que el spec marca como fuente de verdad de la evidencia.
    shipment_item es opcional: dice a qué producto del remito corresponde la foto
    (null = documenta el remito completo).
    """

    class Meta:
        model = Evidence
        fields = [
            "id",
            "shipment",
            "shipment_item",
            "type",
            "uploaded_by",
            "file_url",
            "uploaded_at",
        ]
        read_only_fields = fields


class ShipmentSerializer(serializers.ModelSerializer):
    """Serializer de Shipment para list/create/detail del operador (ver sección 5).

    company y operator NO se toman del payload: se fijan en la vista a partir del
    usuario autenticado (aislamiento multi-tenant, sección 2.2). status, public_token
    y los timestamps del ciclo de despacho son de solo lectura acá: el remito se crea
    siempre en draft y el despacho es una tarea aparte (2.3). Los items se muestran
    anidados de solo lectura; se gestionan por el endpoint propio (tarea 2.2). Las
    evidencias también van anidadas de solo lectura (tarea 2.8): el detalle del remito
    en el frontend muestra las fotos ya subidas, y se suben por su endpoint (tarea 2.4).
    """

    items = ShipmentItemSerializer(many=True, read_only=True)
    evidence = EvidenceSerializer(many=True, read_only=True)

    class Meta:
        model = Shipment
        fields = [
            "id",
            "company",
            "operator",
            "receiver_name",
            "receiver_email",
            "receiver_phone",
            "status",
            "dispatched_at",
            "public_token",
            "link_opened_at",
            "response_deadline",
            "dispute_reason",
            "auto_closed",
            "created_at",
            "items",
            "evidence",
        ]
        read_only_fields = [
            "id",
            "company",
            "operator",
            "status",
            "dispatched_at",
            "public_token",
            "link_opened_at",
            "response_deadline",
            # Lo escribe únicamente el receptor desde el endpoint público de dispute.
            "dispute_reason",
            # Lo escribe únicamente la tarea periódica de cierre automático (3.3).
            "auto_closed",
            "created_at",
        ]


class PublicShipmentItemSerializer(serializers.ModelSerializer):
    """Ítem del remito tal como lo ve el receptor (tarea 3.1). Solo lectura.

    No expone el id del Product: es una entidad interna del catálogo de la empresa
    emisora y el receptor no tiene ningún endpoint donde usarlo. Lo que necesita para
    controlar la carga es qué producto es, cuánto y en qué unidad.
    """

    product_name = serializers.CharField(source="product.name", read_only=True)
    product_unit = serializers.CharField(source="product.unit", read_only=True)

    class Meta:
        model = ShipmentItem
        fields = ["id", "product_name", "product_unit", "quantity", "notes"]
        read_only_fields = fields


class PublicEvidenceSerializer(serializers.ModelSerializer):
    """Foto de evidencia tal como la ve el receptor (tarea 3.1). Solo lectura.

    No expone uploaded_by: es un User de la empresa emisora y el receptor no está
    autenticado. uploaded_at sí, porque es el timestamp certificado del servidor y
    es justamente lo que el receptor tiene que poder ver. shipment_item dice de qué
    producto del remito es la foto (null = del remito completo), y su id ya viaja en
    `items`, así que no expone nada nuevo.
    """

    class Meta:
        model = Evidence
        fields = ["id", "shipment_item", "type", "file_url", "uploaded_at"]
        read_only_fields = fields


class PublicShipmentSerializer(serializers.ModelSerializer):
    """Remito tal como lo ve el receptor en el link público (sección 5, tarea 3.1).

    Es un serializer aparte del ShipmentSerializer del operador a propósito: este
    responde a un endpoint SIN autenticación, así que expone lo mínimo necesario y
    nada de lo interno de la empresa emisora (ids de company/operator/product, email
    y teléfono del receptor). company_name sí, para que el receptor sepa quién le
    despachó el remito.
    """

    company_name = serializers.CharField(source="company.name", read_only=True)
    items = PublicShipmentItemSerializer(many=True, read_only=True)
    evidence = serializers.SerializerMethodField()
    reception_evidence = serializers.SerializerMethodField()

    class Meta:
        model = Shipment
        fields = [
            "id",
            "company_name",
            "receiver_name",
            "status",
            "dispatched_at",
            "link_opened_at",
            "response_deadline",
            "dispute_reason",
            # Para que el receptor que vuelve tarde al link entienda por qué el
            # remito figura aceptado sin que él haya respondido (tarea 3.3).
            "auto_closed",
            "items",
            "evidence",
            "reception_evidence",
        ]
        read_only_fields = fields

    def _photos(self, shipment, evidence_type):
        # El filtro se hace en Python sobre el prefetch_related de la vista, así que
        # no agrega una query por cada tipo.
        photos = [e for e in shipment.evidence.all() if e.type == evidence_type]
        return PublicEvidenceSerializer(photos, many=True).data

    def get_evidence(self, shipment):
        # Las fotos del OPERADOR: es lo que el receptor revisa para decidir si acepta
        # o disputa. Se mantiene bajo la clave `evidence` (contrato de la tarea 3.1).
        return self._photos(shipment, Evidence.DISPATCH)

    def get_reception_evidence(self, shipment):
        # Las fotos que sacó el PROPIO receptor: las necesita a la vista mientras
        # arma la queja, para saber qué lleva sacado antes de confirmar (tarea 3.2).
        return self._photos(shipment, Evidence.RECEPTION)


class BaseEvidenceUploadSerializer(serializers.Serializer):
    """Validación del archivo de una foto de evidencia (payload multipart).

    Solo valida la entrada; el registro de Evidence lo crea la vista después de subir
    el archivo a R2. Lo comparten la evidencia de despacho (operador autenticado) y la
    de recepción (receptor por el link público), porque la foto se valida igual en
    los dos casos.
    """

    # FileField + chequeo de content type, no ImageField: ImageField exige Pillow
    # (no está en el stack de la sección 1.1) y además rechazaría los HEIC que manda
    # la cámara del iPhone, que es justamente el caso de uso del operador.
    file = serializers.FileField()
    # Opcional: id del ítem del remito que documenta la foto. Se valida contra los
    # ítems de ESE remito en la vista (acá no se conoce el remito). Sin él, la foto
    # queda a nivel remito, como venía siendo hasta la tarea 3.2.
    shipment_item = serializers.IntegerField(required=False, allow_null=True)

    def validate_file(self, upload):
        content_type = (upload.content_type or "").lower()
        if not content_type.startswith("image/"):
            raise serializers.ValidationError(
                "La evidencia debe ser una imagen. "
                f"Se recibió un archivo de tipo '{upload.content_type}'."
            )
        return upload


class EvidenceUploadSerializer(BaseEvidenceUploadSerializer):
    """Payload de POST /api/shipments/{id}/evidence/ (multipart).

    `type` es opcional y solo admite 'dispatch': la evidencia de recepción se sube por
    el flujo público del receptor (tarea 3.2), no por este endpoint.
    """

    type = serializers.ChoiceField(
        choices=Evidence.TYPE_CHOICES, required=False, default=Evidence.DISPATCH
    )

    def validate_type(self, value):
        if value != Evidence.DISPATCH:
            raise serializers.ValidationError(
                "Este endpoint solo acepta evidencia de despacho (type='dispatch'). "
                "La evidencia de recepción se sube desde el link público del receptor."
            )
        return value


class ReceptionEvidenceUploadSerializer(BaseEvidenceUploadSerializer):
    """Payload de POST /api/public/shipment/{token}/evidence/ (multipart, tarea 3.2).

    Es la foto que saca el RECEPTOR mientras revisa la carga, antes de confirmar la
    queja. Solo el archivo (+ el ítem opcional): el `type` lo fija la vista en
    'reception' (el receptor no elige el tipo) y `uploaded_by` queda en null porque
    el receptor no tiene usuario.
    """


class DisputeSerializer(serializers.Serializer):
    """Payload de POST /api/public/shipment/{token}/dispute/ (tarea 3.2).

    La foto NO viaja acá: el receptor la sube antes, de a una, por el endpoint de
    evidencia de recepción (mismo patrón que el operador en la tarea 2.8). Este
    endpoint solo cierra la queja, y para eso exige que ya haya al menos una foto
    (sección 5: "registra queja con foto"). El texto es opcional: la evidencia
    obligatoria es la foto y el receptor puede estar apurado en el portón.
    """

    dispute_reason = serializers.CharField(required=False, allow_blank=True)
