from rest_framework.views import APIView
from rest_framework.viewsets import ViewSet
from rest_framework.response import Response
from rest_framework.parsers import MultiPartParser, FormParser
from rest_framework import status
from django.contrib.auth import get_user_model
from .serializers import (
    GetUserSerializer, SetPasswordSerializer,
    UpdateUserSerializer, AddImageProfileSerializer,
    OrderImageProfileSerializer,ProfileImagerSerializer,
    DeletePasswordSerializer
)

from .models import User, Profile
from rest_framework.permissions import IsAuthenticated
from rest_framework_simplejwt.authentication import JWTAuthentication

from django.utils.translation import gettext as _


class UserAPIView(APIView):
    authentication_classes = [JWTAuthentication]
    permission_classes     = [IsAuthenticated]
    def get(self, request):
       
        user = request.user
        
        serializer = GetUserSerializer(user)
        return Response(
            {"user": serializer.data, "message": _("success::user found.")},
            status=status.HTTP_200_OK
        )
    
    
    def put(self, request):
      
        user = request.user

        serializer = UpdateUserSerializer(instance=user, data=request.data)
        
        if serializer.is_valid():
            serializer.update(user, serializer.validated_data)
            return Response(
                {"user": serializer.data, "message": _("success::user updated.")},
                status=status.HTTP_200_OK
            )

        return Response(
            {"user": {}, "message": _("error::user not updated!"), "errors": serializer.errors},
            status=status.HTTP_400_BAD_REQUEST
    )


class ProfileViewSet(ViewSet):
    authentication_classes = [JWTAuthentication]
    permission_classes     = [IsAuthenticated]
    parser_classes = [MultiPartParser, FormParser]
    
    def list(self, request):
        user = request.user
        profiles = Profile.objects.filter(user=user).order_by("order", "created_at")
        serializer = ProfileImagerSerializer(profiles, many=True, context={"request":request})
        return Response(serializer.data)
    

    def order(self, request):
        user = request.user

        lst_order = request.data
        
        serializer = OrderImageProfileSerializer(data=lst_order)
        if serializer.is_valid():
            serializer.save(user)
            return Response(data={"message": _("success::order change.")}, status=status.HTTP_200_OK)
        return Response({"message": _("error::cant change order."), "errors": serializer.errors},status=status.HTTP_400_BAD_REQUEST)
        
    def delete(self, request):
        user = request.user
        try:
            profile = Profile.objects.get(pk=id, user=user)
            profile.delete()
        except Profile.DoesNotExist:
            return Response(
                {"message": _("error::profile not found!")},
                status=status.HTTP_404_NOT_FOUND
            )
        
        
        return Response(data={"message": _("success::profile deleted.")}, status=status.HTTP_200_OK)
        
    def set(self, request):

        user = request.user
        serializer = AddImageProfileSerializer(data=request.data)
        if serializer.is_valid():
            serializer.save(user)
            return Response(data={"message": _("success::profile added.")}, status=status.HTTP_200_OK)
        return Response({"message": _("error::cant add profile."), "errors": serializer.errors},status=status.HTTP_400_BAD_REQUEST)
                
        
class PasswordViewSet(ViewSet):
    authentication_classes = [JWTAuthentication]
    permission_classes     = [IsAuthenticated]
    def set(self, request):
        user = request.user
        serializer = SetPasswordSerializer(data=request.data)
        if serializer.is_valid():
            serializer.save(user)
            return Response(data={"message": _("success::password changed.")}, status=status.HTTP_200_OK)
        
        return Response({"message": _("error::cant set password."), "errors": serializer.errors},status=status.HTTP_400_BAD_REQUEST)
            
    def delete(self, request):
        user = request.user
        
        serializer = DeletePasswordSerializer(data=request.data)
        
        if serializer.is_valid(user=user):
            serializer.save()
            return Response(data={"message": _("success::password deleted.")}, status=status.HTTP_200_OK)
            
        return Response({"message": _("error::cant set password."), "errors": serializer.errors},status=status.HTTP_400_BAD_REQUEST)