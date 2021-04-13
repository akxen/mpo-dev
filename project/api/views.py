from rest_framework import status
from rest_framework.views import APIView
from rest_framework.response import Response

from .serializers import ModelDataSerializer
from .optimisation.model import run_model


class RunModel(APIView):
    """Construct, run, and solve model with data posted by user"""

    def post(self, request, format=None):
        serializer = ModelDataSerializer(data=request.data)

        if serializer.is_valid():
            result = run_model(data=serializer.data)
            return Response(result)

        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
