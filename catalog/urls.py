from django.urls import path

from .views import ProductByBarcodeView, ProductExportQRsView, ProductListView

urlpatterns = [
    path("products/", ProductListView.as_view(), name="product-list"),
    path(
        "products/by-barcode/",
        ProductByBarcodeView.as_view(),
        name="product-by-barcode",
    ),
    path(
        "products/export-qrs/",
        ProductExportQRsView.as_view(),
        name="product-export-qrs",
    ),
]
