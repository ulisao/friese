from django.http import HttpResponse
from rest_framework import generics, status
from rest_framework.authentication import SessionAuthentication
from rest_framework.exceptions import NotFound
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.authentication import JWTAuthentication

from .models import Product
from .qr_export import build_qr_pdf
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


class ProductExportQRsView(APIView):
    """GET /api/products/export-qrs/ — tarea 11.5.

    PDF con un QR por producto de la company del usuario autenticado, listo
    para imprimir y pegar en la góndola (sección "El flujo completo con 11.5").
    No hay pantalla de productos en el frontend: hoy se gestionan desde el
    Django Admin, así que además del JWT de siempre se acepta la cookie de
    sesión del admin — el botón "Descargar QRs para imprimir" del listado de
    productos es un link común, y el navegador lo pide con esa cookie, no con
    un Bearer token.
    """

    authentication_classes = [JWTAuthentication, SessionAuthentication]
    permission_classes = [IsAuthenticated]

    def get(self, request):
        if request.user.is_superuser:
            queryset = Product.objects.all()
        else:
            queryset = Product.objects.filter(company=request.user.company)
        products = queryset.order_by("name")

        pdf_bytes = build_qr_pdf(products)
        response = HttpResponse(pdf_bytes, content_type="application/pdf")
        response["Content-Disposition"] = 'attachment; filename="qrs-productos.pdf"'
        return response
