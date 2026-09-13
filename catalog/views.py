from rest_framework import generics, status
from rest_framework.exceptions import NotFound
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import Product
from .serializers import ProductSerializer


class ProductListView(generics.ListAPIView):
    """GET /api/products/ — productos de la empresa del operador (sección 5).

    Filtra por la company del usuario autenticado (aislamiento multi-tenant,
    sección 2.2) y devuelve solo los productos activos: la lista alimenta el
    selector de productos del remito, donde un producto dado de baja no debe
    poder elegirse.
    """

    serializer_class = ProductSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return Product.objects.filter(
            company=self.request.user.company, is_active=True
        ).order_by("name")


class ProductByBarcodeView(APIView):
    """GET /api/products/by-barcode/?code={code} — tarea 11.2.

    Busca un producto de la company del usuario autenticado cuyo `barcode`
    coincida exacto (case-sensitive) con `code`. Si hay más de un producto con
    el mismo código (no debería pasar) devuelve el primero. No filtra por
    `is_active`: un código escaneado debe encontrarse aunque el producto esté
    dado de baja, para que el operador sepa por qué no puede elegirlo.
    """

    permission_classes = [IsAuthenticated]

    def get(self, request):
        code = request.query_params.get("code", "").strip()
        if not code:
            raise NotFound("Código no encontrado")

        product = (
            Product.objects.filter(company=request.user.company, barcode=code)
            .order_by("id")
            .first()
        )
        if product is None:
            raise NotFound("Código no encontrado")

        serializer = ProductSerializer(product)
        return Response(serializer.data, status=status.HTTP_200_OK)
