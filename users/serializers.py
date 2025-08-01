from rest_framework import serializers,  exceptions
from .models import User, Profile, Rule, COLOR_CHOICES
from django.core.exceptions import ValidationError as DjangoValidationError
import json
import string

class CreateUserSerializer(serializers.ModelSerializer):
    email = serializers.EmailField(required=False, allow_blank=True)
    username = serializers.CharField(max_length=150, required=True)
    phone_number = serializers.CharField(
        max_length=11,
        required=False,
        allow_blank=True,
    )

    class Meta:
        model = User
        fields = ["username", "email", "phone_number"]
        extra_kwargs = {
            "username": {"write_only": True},
            "email": {"write_only": True},
            "phone_number": {"write_only": True}
        }

    def validate(self, data):
        if data.get("email") or data.get("phone_number"):
            raise serializers.ValidationError("Either email or phone number must be set.")

        # email = data.get("email")
        # phone_number = data.get("phone_number")
        
        
        # MAX_PER_EMAIL = 2
        # MAX_PER_PHONE = 2
        
        # if email:
        #     count = User.objects.filter(email=email).count()
        #     if count >= MAX_PER_EMAIL:
        #         raise serializers.ValidationError({"email": f"too many accounts registered with this email {email}"})
        

        # if phone_number:
        #     count = User.objects.filter(phone_number=phone_number).count()
        #     if count >= MAX_PER_PHONE:
        #         raise serializers.ValidationError({"phone_number": f"too many account registered with this phone number {phone_number}"})

        return data  

        
    def create(self, validated_data):
        username = validated_data.get("username", "")
        email = validated_data.get("email", "")
        phone_number = validated_data.get("phone_number", "")

        user = User(
            username=username,
            email=email,
            phone_number=phone_number,
            is_active=False
        )
        
        try:
            user.full_clean() 
            user.save()
        except DjangoValidationError as e:
            raise exceptions.ValidationError(e.message_dict)
        except Exception as e:
            raise exceptions.ValidationError(e)
            
        return user
        
class GetUserSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ["id", "username", "email", "phone_number", "theme", "email_verified", "phone_number_verified", "color", "birthdate"]
        extra_kwargs = {
            "id" : {"read_only": True},
            "username": {"read_only": True},
            "email" : {"read_only": True},
            "phone_number" : {"read_only": True},
            "theme": {"read_only": True},
            "color": {"read_only": True},
            "email_verified": {"read_only": True},
            "email_verified": {"read_only": True},
            "birthdate": {"read_only": True},
        }

class SetPasswordSerializer(serializers.Serializer):
    password = serializers.CharField(write_only = True, min_length=8)
    confirm_password = serializers.CharField(write_only = True, min_length=8)

    def validate(self, data):
        if data["password"] != data["confirm_password"]:
            raise serializers.ValidationError("Password do not match")
        return data

    def save(self, user):
        user.set_password(self.validated_data["password"])
        user.save()
        return user

class UpdateUserSerializer(serializers.Serializer):
    email = serializers.EmailField(required=False, allow_blank=False)
    username = serializers.CharField(max_length=150, required=False)
    phone_number = serializers.CharField(
        max_length=11,
        allow_blank=True,
        required=False
    )
    
    birthdate = serializers.DateField(required=False)
    theme = serializers.ChoiceField(choices=User.ThemeChoices.choices)
    color = serializers.ChoiceField(choices=COLOR_CHOICES)

    def validate(self, data):
        return CreateUserSerializer.validate(self, data)
    def update(self, user, data):
        username = data.get("username", "")
        phone_number = data.get("phone_number", "")
        email = data.get("email", "")
        birthdate = data.get("birthdate", "")
        theme = data.get("theme", "")
        color = data.get("color", "")
        
        if username:
            user.username = username
        if phone_number:
            user.phone_number = phone_number
            user.phone_number_verified=False
            
        if email:
            user.email = email
            user.email_verified=False
        if birthdate:
            user.birthdate = birthdate
        if color:
            user.theme = theme
        if theme:
            user.color = color
   
        try:
            user.full_clean() 
            user.save()
        except DjangoValidationError as e:
            raise exceptions.ValidationError(e.message_dict)
        except Exception as e:
            raise exceptions.ValidationError(e)
        return user


class AddImageProfileSerializer(serializers.Serializer):
    image = serializers.ImageField(write_only=True)
    order = serializers.IntegerField(write_only=True)
    
    def save(self, user):
        order = self.validated_data.get("order", -1)
        profile = Profile(user=user, order=order, image=self.validated_data["image"])
        try:
            profile.full_clean() 
            profile.save()
        except DjangoValidationError as e:
            raise exceptions.ValidationError(e.message_dict)
        except Exception as e:
            raise exceptions.ValidationError(e)
        return profile
    
    
class OrderImageProfileSerializer(serializers.Serializer):
    order = serializers.JSONField(write_only=True)
    def validate(self, data):
        order = data.get("order", None)
        if order and isinstance(order, dict):
            if not all([i.isdigit() for i in order.keys()]):
                raise exceptions.ValidationError("order keys should be inlcude digits")
            if not all([isinstance(i, int) for i in order.values()]):
                raise exceptions.ValidationError("order values should be a integer")
        else:
            raise exceptions.ValidationError("order should be a dict(json=>{key:value}) that is not empty")
        return data 
    def save(self, user):
        profile_images =  Profile.objects.filter(user=user)
        profile_images = {str(i.id):i for i in profile_images}
        order = self.validated_data["order"]
        for i in order:
            try:
                profile_images[i].order = int(order[i])
                profile_images[i].save()
            except KeyError:
                pass
        return order
    
class ProfileImagerSerializer(serializers.ModelSerializer):
    image_url = serializers.SerializerMethodField(read_only=True)

    class Meta:
        model = Profile
        fields = ["id", "order", "image_url"]

    
                
    def get_image_url(self, obj):
        request = self.context.get("request", None)
        if obj.image and request and hasattr(obj.image, "url"):
            return request.build_absolute_uri(obj.image.url) if request else obj.image.url
        return None
