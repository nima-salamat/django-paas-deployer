from django.db import models
from django.contrib.auth.models import AbstractBaseUser, UserManager, Permission
from phonenumber_field.modelfields import PhoneNumberField
from django.utils.translation import gettext_lazy as _
from django.utils import timezone
import uuid
import random

class PermissionMixin(models.Model):
    is_superuser = models.BooleanField(
        _("superuser status"),
        default=False,
        help_text=_(
            "User has all permission without"
            " explicitly assigning them."
        )
    )
    
    class Meta:
        abstract = True
    def has_perm(self, perm, obj=None):
        return self.is_active & self.is_superuser
    
    def has_perms(self, perm_list, obj=None):
        return self.is_active & self.is_superuser
    
    def has_module_perms(self, app_label):
        return self.is_active & self.is_superuser

def get_uuid():
    return uuid.uuid4().hex

COLORS = [
        "#1abc9c","#2ecc71","#3498db", "#9b59b6","#34495e",
        "#16a085", "#27ae60", "#2980b9", "#8e44ad", "#2c3e50",
        "#f1c40f", "#e67e22", "#e74c3c", "#ecf0f1", "#95a5a6",
        "#f39c12", "#d35400", "#c0392b", "#bdc3c7", "#7f8c8d",
        
    ]
COLOR_CHOICES = [(i,j) for i, j in enumerate(COLORS, 0)]


def get_color():
    
    return random.choice(COLOR_CHOICES)[0]
    
     


class User(AbstractBaseUser, PermissionMixin):
    class ThemeChoices(models.TextChoices):
        DARK = "dark"
        LIGHT = "light"
    uuid = models.CharField(max_length=255, editable=False, null=False, blank=False, unique=True, default=get_uuid)
    username = models.CharField(_("username"), unique=True, max_length=255, unique=True,
        help_text=_("Required. 32 characters or fewer. Include numbers, letters and ./-/_ characters."),
    )
    email = models.EmailField(_("email address"), max_length=255, null=True, blank=True, unique=True)
    email_verified = models.BooleanField(_("email verified"), default=False)
    phone_number = PhoneNumberField(_("phone number"), null=True, blank=True)
    phone_number_verified = models.BooleanField(_("phone number verified"), default=False)
    theme = models.CharField(_("theme"), choices=ThemeChoices.choices, default=ThemeChoices.LIGHT)
    color = models.PositiveSmallIntegerField(_("color"), choices=COLOR_CHOICES, default=get_color())    
    is_staff = models.BooleanField(
        _("staff status"),
        default=False,
        help_text=_("Designates whether the user can log into this admin site."),
    )
    is_active = models.BooleanField(
        _("active"),
        default=True,
        help_text=_(
            "Designates whether this user should be treated as active. "
            "Unselect this instead of deleting accounts."
        ),
    )
    date_joined = models.DateTimeField(_("date joined"), default=timezone.now)


    USERNAME_FIELD = "username"
    REQUIRED_FIELDS = ["email"]
    

    
        

    