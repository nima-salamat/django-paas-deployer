from django.db import models
from django.contrib.auth.models import AbstractBaseUser, UserManager
from phonenumber_field.modelfields import PhoneNumberField
from django.core.exceptions import ValidationError
from django.core.files.images import get_image_dimensions
from django.utils.deconstruct import deconstructible
from django.utils.translation import gettext_lazy as _
from django.contrib.postgres.fields import ArrayField
from django.utils import timezone
import uuid
import random


@deconstructible
class ImageValidator:
    def __init__(self, size_kb, max_w, max_h):
        self.size_kb = size_kb
        self.max_w = max_w
        self.max_h = max_h

    def __call__(self, pic):
        w, h = get_image_dimensions(pic)
        size_kb = pic.size // 1024
        if w <= self.max_w and h <= self.max_h and size_kb <= self.size_kb:
            return
        raise ValidationError(
            _(f"Image file size must be ≤ {self.size_kb} KB and dimensions ≤ {self.max_w}×{self.max_h}px.")
        )

class PermissionMixin(models.Model):
    is_superuser = models.BooleanField(
        _("superuser status"),
        default=False,
        help_text=_(
          "User has all permissions without explicitly assigning them."
        )
    )
    
    class Meta:
        abstract = True
    def has_perm(self, perm, obj=None):
        return self.is_active and self.is_superuser
    
    def has_perms(self, perm_list, obj=None):
        return self.is_active and self.is_superuser
    
    def has_module_perms(self, app_label):
        return self.is_active and self.is_superuser

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
        DARK  = "dark",  _("Dark")
        LIGHT = "light", _("Light")

    uuid = models.CharField(max_length=32, editable=False, null=False, blank=False, unique=True, default=get_uuid)
    username = models.CharField(_("username"), unique=True, max_length=32, 
        help_text=_("Required. 32 characters or fewer. Include numbers, letters and ./-/_ characters."),
    )
    email = models.EmailField(_("email address"), max_length=255, null=True, blank=True, unique=True)
    email_verified = models.BooleanField(_("email verified"), default=False)
    phone_number = PhoneNumberField(_("phone number"), null=True, blank=True, unique=True)
    phone_number_verified = models.BooleanField(_("phone number verified"), default=False)
    theme = models.CharField(_("theme"), choices=ThemeChoices.choices, default=ThemeChoices.LIGHT, max_length=7)
    color = models.PositiveSmallIntegerField(_("color"), choices=COLOR_CHOICES, default=get_color)    
    birthdate = models.DateField(_("birth date"),null=True, blank=True)

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
    objects = UserManager()
    
    class Meta:
        ordering = ["username"]
        verbose_name = "user"
        verbose_name_plural = "users"


class Profile(models.Model):
    order = models.IntegerField(default=0)
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    image = models.ImageField(upload_to="images", validators=[ImageValidator(size_kb=2048, max_w=2560, max_h=1440)])
    created_at = models.DateTimeField(default=timezone.now)
    def clean(self):
        if self.pk is None:
            if Profile.objects.filter(user=self.user).count() >=5:
                raise ValidationError(_("A user can have at most 5 profiles."))
            
    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.user}-{self.order}"


class Rule(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, verbose_name= _("user rule"), related_name="rule")
    rules = ArrayField(
        base_field=models.CharField(max_length=100),
        blank=True,
        default=list
    )
    updated_at = models.DateTimeField(auto_now=True)
    created_at = models.DateTimeField(default=timezone.now)
    
    def __str__(self):
        return f"{self.user.username}"
    