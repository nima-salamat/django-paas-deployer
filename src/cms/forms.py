"""
Wagtail user forms for users.User (AbstractBaseUser + PermissionsMixin).
"""
from __future__ import annotations

from django.contrib.auth import get_user_model
from wagtail.users.forms import UserCreationForm as WagtailUserCreationForm
from wagtail.users.forms import UserEditForm as WagtailUserEditForm

User = get_user_model()


class CustomUserEditForm(WagtailUserEditForm):
    class Meta(WagtailUserEditForm.Meta):
        model = User
        fields = [
            "username",
            "first_name",
            "last_name",
            "email",
            "is_active",
            "is_staff",
            "is_superuser",
            "groups",
            "user_permissions",
        ]


class CustomUserCreationForm(WagtailUserCreationForm):
    class Meta(WagtailUserCreationForm.Meta):
        model = User
        fields = [
            "username",
            "first_name",
            "last_name",
            "email",
            "is_active",
            "is_staff",
            "is_superuser",
            "groups",
            "user_permissions",
        ]
