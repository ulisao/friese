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
    """

    class Meta:
        model = Evidence
        fields = [
            "id",
            "shipment",
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
            "created_at",
        ]


class EvidenceUploadSerializer(serializers.Serializer):
    """Payload de POST /api/shipments/{id}/evidence/ (multipart).

    Solo valida la entrada; el registro de Evidence lo crea la vista después de subir
    el archivo a R2. `type` es opcional y solo admite 'dispatch': la evidencia de
    recepción se sube por el flujo público del receptor (Fase 3), no por este endpoint.
    """

    # FileField + chequeo de content type, no ImageField: ImageField exige Pillow
    # (no está en el stack de la sección 1.1) y además rechazaría los HEIC que manda
    # la cámara del iPhone, que es justamente el caso de uso del operador.
    file = serializers.FileField()
    type = serializers.ChoiceField(
        choices=Evidence.TYPE_CHOICES, required=False, default=Evidence.DISPATCH
    )

    def validate_file(self, upload):
        content_type = (upload.content_type or "").lower()
        if not content_type.startswith("image/"):
            raise serializers.ValidationError(
                "La evidencia debe ser una imagen. "
                f"Se recibió un archivo de tipo '{upload.content_type}'."
            )
        return upload

    def validate_type(self, value):
        if value != Evidence.DISPATCH:
            raise serializers.ValidationError(
                "Este endpoint solo acepta evidencia de despacho (type='dispatch'). "
                "La evidencia de recepción se sube desde el link público del receptor."
            )
        return value
