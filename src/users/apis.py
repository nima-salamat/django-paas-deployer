from rest_framework.views import APIView
from rest_framework.viewsets import ViewSet
from rest_framework.response import Response
from rest_framework.parsers import MultiPartParser, FormParser, JSONParser
from rest_framework import status
from django.contrib.auth import get_user_model
from .serializers import (
    GetUserSerializer,
    SetPasswordSerializer,
    ChangePasswordSerializer,
    RemovePasswordSerializer,
    UpdateUserSerializer,
    AddImageProfileSerializer,
    OrderImageProfileSerializer,
    ProfileImagerSerializer,
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
    # parser_classes = [MultiPartParser, FormParser]
    
    def get_parser_classes(self):
        if self.action == "order":
            return [JSONParser]
        return [MultiPartParser, FormParser]
    
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
        id = request.data.get("id", "")
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


        
class PasswordStatusAPIView(APIView):
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAuthenticated]

    def get(self, request):
        user = request.user
        return Response(
            {
                "has_password": user.has_usable_password(),
                "message": _("success::password status retrieved."),
            },
            status=status.HTTP_200_OK,
        )


class SetPasswordAPIView(APIView):
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAuthenticated]

    def post(self, request):
        serializer = SetPasswordSerializer(data=request.data)
        if serializer.is_valid():
            serializer.save(request.user)
            return Response({"message": _("success::password set.")}, status=status.HTTP_200_OK)
        return Response({"message": _("error::cannot set password."), "errors": serializer.errors}, status=status.HTTP_400_BAD_REQUEST)
            
class ChangePasswordAPIView(APIView):
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAuthenticated]

    def post(self, request):
        serializer = ChangePasswordSerializer(data=request.data, user=request.user)
        if serializer.is_valid():
            serializer.save()
            return Response({"message": _("success::password changed.")}, status=status.HTTP_200_OK)
        return Response({"message": _("error::cannot change password."), "errors": serializer.errors}, status=status.HTTP_400_BAD_REQUEST)


class RemovePasswordAPIView(APIView):
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAuthenticated]

    def delete(self, request):
        serializer = RemovePasswordSerializer(data=request.data, user=request.user)
        if serializer.is_valid():
            serializer.save()
            return Response({"message": _("success::password removed.")}, status=status.HTTP_200_OK)
        return Response({"message": _("error::cannot remove password."), "errors": serializer.errors}, status=status.HTTP_400_BAD_REQUEST)