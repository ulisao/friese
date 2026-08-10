from django.urls import path
from rest_framework.routers import DefaultRouter

from .views import (
    PublicReceptionEvidenceView,
    PublicShipmentAcceptView,
    PublicShipmentDisputeView,
    PublicShipmentView,
    ShipmentItemViewSet,
    ShipmentViewSet,
)

# Router genera GET/POST /api/shipments/ y GET /api/shipments/{id}/ (ver sección 5).
router = DefaultRouter()
router.register(r"shipments", ShipmentViewSet, basename="shipment")

# Items anidados bajo el remito (tarea 2.2). Sin nested-routers de terceros: se arma
# a mano el mapeo de métodos → acciones del ModelViewSet.
shipment_item_list = ShipmentItemViewSet.as_view(
    {"get": "list", "post": "create"}
)
shipment_item_detail = ShipmentItemViewSet.as_view(
    {
        "get": "retrieve",
        "put": "update",
        "patch": "partial_update",
        "delete": "destroy",
    }
)

urlpatterns = router.urls + [
    path(
        "shipments/<int:shipment_pk>/items/",
        shipment_item_list,
        name="shipment-item-list",
    ),
    path(
        "shipments/<int:shipment_pk>/items/<int:pk>/",
        shipment_item_detail,
        name="shipment-item-detail",
    ),
    # Link público del receptor (tarea 3.1). El converter <uuid:> hace que un token
    # con formato inválido dé 404 en el ruteo, sin llegar a la vista ni a la DB.
    path(
        "public/shipment/<uuid:token>/",
        PublicShipmentView.as_view(),
        name="public-shipment",
    ),
    # Respuesta del receptor (tarea 3.2): fotos de recepción de a una, y después
    # conformidad o queja.
    path(
        "public/shipment/<uuid:token>/evidence/",
        PublicReceptionEvidenceView.as_view(),
        name="public-shipment-evidence",
    ),
    path(
        "public/shipment/<uuid:token>/accept/",
        PublicShipmentAcceptView.as_view(),
        name="public-shipment-accept",
    ),
    path(
        "public/shipment/<uuid:token>/dispute/",
        PublicShipmentDisputeView.as_view(),
        name="public-shipment-dispute",
    ),
]
