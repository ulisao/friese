from rest_framework import status
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from .serializers import RegisterOperatorSerializer


class RegisterOperatorView(APIView):
    """POST /api/auth/register-operator/ — alta de operador vía token de invitación.

    Endpoint público (sin auth): el operador aún no tiene credenciales. La
    validación del token vive en el serializer. Ver docs/desarrollo.md sección 4.
    """

    permission_classes = [AllowAny]

    def post(self, request):
        serializer = RegisterOperatorSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(
            {"detail": "Operador registrado."}, status=status.HTTP_201_CREATED
        )
