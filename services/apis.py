from .models import Service, PrivateNetwork
from .serializers import PrivateNetworkSerializer, ServiceSerializer
from rest_framework.viewsets import ViewSet
from rest_framework.response import Response
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework_simplejwt.authentication import JWTAuthentication


# class ServiceViewSet(ViewSet):
#     authentication_classes = [JWTAuthentication]
#     permission_classes = [IsAuthenticated]

# NOT IMPLEMENTED YET