from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework import status
from rest_framework_simplejwt.exceptions import AuthenticationFailed
from rest_framework_simplejwt.tokens import RefreshToken
from users.models import User
from users.serializers import CreateUserSerializer
from .models import AuthCode
from core.tasks.email import send_code_via_email
import logging

logger = logging.getLogger("auth_users.apis")

def get_tokens_for_user(user):
    if not user.is_active:
      raise AuthenticationFailed("User is not active")

    refresh = RefreshToken.for_user(user)

    return {
        'refresh': str(refresh),
        'access': str(refresh.access_token),
    }

class AuthAPIView(APIView):
    def post(self, request):
        username = request.data.get("username", "")
        email = request.data.get("email", "")
        phone_number = request.data.get("phone_number", "")
        password = request.data.get("password", "")
        code = request.data.get("code", "")

        if not username:
            return Response({"message": "error::username is required"}, status=status.HTTP_400_BAD_REQUEST)
  
        if not any([email, phone_number]):
            return Response({"message": "error::email or phone number is required"}, status=status.HTTP_400_BAD_REQUEST)

        data = {"username":username}

        if email:
            data["email"] = email
        if phone_number:
            data["phone_number"] = phone_number
        try:
            user = User.objects.get(**data)
            if user.password:
                if not user.check_password(password):
                    return Response({"message": "error::password is incorrect"}, status=status.HTTP_400_BAD_REQUEST)
 
                
            if not AuthCode.code_is_valid(user, code):
                return Response({"message": "error::code is incorrect"}, status=status.HTTP_400_BAD_REQUEST)

            user.is_active = True
            if email:
                user.email_verified = True
            if phone_number:
                user.phone_number_verified = True
            user.save()
            AuthCode.objects.filter(user=user).delete()
                
        except User.DoesNotExist:
            return Response({"message": "error::user not found"}, status=status.HTTP_404_NOT_FOUND)

        
        return Response({**get_tokens_for_user(user), "message":"success::user logged in"})


class ValidateAPIView(APIView):
    def post(self, request):
        username = request.data.get("username", "")
        email = request.data.get("email", "")
        phone_number = request.data.get("phone_number", "")
        code = request.data.get("code", "")

        if not username:
            return Response({"message": "error::username is required"}, status=status.HTTP_400_BAD_REQUEST)
  
        if not any([email, phone_number]):
            return Response({"message": "error::email or phone number is required"}, status=status.HTTP_400_BAD_REQUEST)

        data = {"username":username}
        
        
        if email:
            
            data["email"] = email
        if phone_number:
            data["phone_number"] = phone_number
        try:
            user = User.objects.get(**data)
            if not AuthCode.code_is_valid(user, code):
                return Response({"message": "error::code is incorrect"}, status=status.HTTP_400_BAD_REQUEST)
            user.is_active = True
            if email:
            
                user.email_verified = True
            if phone_number:
                user.phone_number_verified = True
            user.save()
             
        except User.DoesNotExist:
            return Response({"message": "error::user not found"}, status=status.HTTP_404_NOT_FOUND)

        
        return Response({"is_valid": True, "message":"success::user is valid"})




class LoginAPIView(APIView):
    def post(self, request):
        username = request.data.get("username", "")
        email = request.data.get("email", "")
        phone_number = request.data.get("phone_number", "")
 
        if not username:
            return Response({"message":"error::username is required"},status=status.HTTP_400_BAD_REQUEST)
        if not any([email, phone_number]):
            return Response({"message":"error::email or phone_number is required"},status=status.HTTP_400_BAD_REQUEST)
            
        data = {"username":username}
        
        sent_to = ""
        if email:
            sent_to="email"
            data["email"] = email     
        else:
            sent_to="phone_number"
            data["phone_number"] = phone_number
 
        try:
            user = User.objects.get(**data)
            code = AuthCode.create_code(user)
            if sent_to == "email":
                send_code_via_email.delay(user.id)
            else:
                logger.info(f"Sms is not implemented yet. user:{user.username}, code: {code}")
            
        except User.DoesNotExist:
            return Response({"message":"error::such username does not exist"},status=status.HTTP_404_NOT_FOUND)
        
        return Response({"message":f"success:code sent to your {sent_to}"},status=status.HTTP_200_OK)




class SignupView(APIView):
    def post(self, request):
        username = request.data.get("username", "")
        email = request.data.get("email", "")
        phone_number = request.data.get("phone_number", "")
 
        if not username:
            return Response({"message":"error::username is required"},status=status.HTTP_400_BAD_REQUEST)
        if not any([email, phone_number]):
            return Response({"message":"error::email or phone_number is required"},status=status.HTTP_400_BAD_REQUEST)
        
        user = request.data
        serializer = CreateUserSerializer(data=user)
        
        if serializer.is_valid():
            serializer.save()
            return Response(
                {"user": serializer.data, "message": "success::user created."},
                status=status.HTTP_201_CREATED
            )
        
        return Response(
            {"user": {}, "message": "error::user not created!", "errors": serializer.errors},
            status=status.HTTP_400_BAD_REQUEST
        )
