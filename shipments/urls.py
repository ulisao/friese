from django.urls import path
from rest_framework.routers import DefaultRouter

from .views import ShipmentItemViewSet, ShipmentViewSet

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
]
