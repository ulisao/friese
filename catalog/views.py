from rest_framework import generics
from rest_framework.permissions import IsAuthenticated

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
