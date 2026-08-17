"""Wagtail admin (snippet) registration for the users app.

The custom ``User`` model is the project's ``AUTH_USER_MODEL``.  It is exposed
here as a snippet (so it can be created/edited/deleted from the Wagtail panel)
while continuing to use Wagtail's user forms (``cms.forms``) so that passwords
are hashed correctly.  ``wagtail.users`` still administers the same model from
Settings -> Users.
"""
from __future__ import annotations

from cms.forms import CustomUserCreationForm, CustomUserEditForm
from cms.wagtail_admin.utils import panels_for
from users.models import Profile, Receipt, Rule, User
from wagtail.snippets.views.snippets import SnippetViewSet, SnippetViewSetGroup


class UserViewSet(SnippetViewSet):
    model = User
    icon = "user"
    menu_label = "Users"
    menu_order = 139
    list_display = ["username", "email", "is_active", "is_staff", "is_superuser", "date_joined"]
    list_filter = ["is_active", "is_staff", "is_superuser"]
    search_fields = ["username", "email", "first_name", "last_name"]
    ordering = ["username"]
    panels = [
        *panels_for(
            editable=[
                "username",
                "email",
                "first_name",
                "last_name",
                "phone_number",
                "is_active",
                "is_staff",
                "is_superuser",
                "groups",
                "user_permissions",
            ],
            read_only=[
                "uuid",
                "password",
                "date_joined",
                "email_verified",
                "phone_number_verified",
            ],
        )
    ]

    def get_form_class(self, for_update=False):
        if for_update:
            return CustomUserEditForm
        return CustomUserCreationForm


class ReceiptViewSet(SnippetViewSet):
    model = Receipt
    icon = "doc-full"
    menu_label = "Receipts"
    menu_order = 140
    list_display = ["user", "amount", "status", "created_at", "updated_at"]
    list_filter = ["status", "user"]
    search_fields = ["user__username", "user__email"]
    ordering = ["-created_at"]
    panels = panels_for(
        editable=["user", "amount", "status"],
        read_only=["created_at", "updated_at"],
    )


class ProfileViewSet(SnippetViewSet):
    model = Profile
    icon = "user"
    menu_label = "Profiles"
    menu_order = 141
    list_display = ["user", "order", "created_at"]
    search_fields = ["user__username", "user__email"]
    panels = panels_for(
        editable=["user", "order", "image"],
        read_only=["created_at"],
    )


class RuleViewSet(SnippetViewSet):
    model = Rule
    icon = "list-ul"
    menu_label = "User rules"
    menu_order = 142
    list_display = ["user", "created_at", "updated_at"]
    search_fields = ["user__username"]
    panels = panels_for(
        editable=["user"],
        read_only=["rules", "created_at", "updated_at"],
    )


class UsersGroup(SnippetViewSetGroup):
    items = (
        UserViewSet,
        ProfileViewSet,
        ReceiptViewSet,
        RuleViewSet,
    )
    menu_label = "Users"
    menu_icon = "user"
    menu_order = 140
