from rest_framework import serializers

from .models import Product


class ProductSerializer(serializers.ModelSerializer):
    """Producto del catálogo de la empresa (ver docs/desarrollo.md sección 5).

    Solo lectura: el alta de productos (POST /api/products/) no está en el alcance
    de esta tarea. `unit` viaja con el valor crudo del choice (bolsas | kg | m3 |
    ton | unidad) porque es lo que el frontend muestra junto a la cantidad
    ("50 bolsas"), no el label capitalizado del modelo.
    """

    class Meta:
        model = Product
        fields = [
            "id",
            "name",
            "description",
            "barcode",
            "unit",
        ]
        read_only_fields = fields
