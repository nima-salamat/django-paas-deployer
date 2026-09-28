"""Explicit Wagtail surfaces for user-owned supporting records."""
from __future__ import annotations

from cms.wagtail_admin.utils import ReadOnlyModelPermissionPolicy, panels_for
from users.models import Profile, Receipt, Rule
from wagtail.snippets.views.snippets import SnippetViewSet, SnippetViewSetGroup


class ReceiptViewSet(SnippetViewSet):
    model = Receipt
    permission_policy = ReadOnlyModelPermissionPolicy(Receipt)
    inspect_view_enabled = True
    copy_view_enabled = False
    icon = "doc-full"
    menu_label = "Receipts"
    menu_order = 140
    list_display = ["user", "amount", "status", "created_at", "updated_at"]
    list_filter = ["status", "user"]
    search_fields = ["user__username", "user__email"]
    ordering = ["-created_at"]
    panels = panels_for(editable=[], read_only=["id", "user", "amount", "status", "created_at", "updated_at"])


class ProfileViewSet(SnippetViewSet):
    model = Profile
    icon = "user"
    menu_label = "Profiles"
    menu_order = 141
    list_display = ["user", "order", "created_at"]
    search_fields = ["user__username", "user__email"]
    panels = panels_for(editable=["user", "order", "image"], read_only=["id", "created_at"])


class RuleViewSet(SnippetViewSet):
    model = Rule
    permission_policy = ReadOnlyModelPermissionPolicy(Rule)
    inspect_view_enabled = True
    copy_view_enabled = False
    icon = "list-ul"
    menu_label = "User rules"
    menu_order = 142
    list_display = ["user", "created_at", "updated_at"]
    search_fields = ["user__username"]
    panels = panels_for(editable=[], read_only=["id", "user", "rules", "created_at", "updated_at"])


class UsersGroup(SnippetViewSetGroup):
    items = (ProfileViewSet, ReceiptViewSet, RuleViewSet)
    menu_label = "Users"
    menu_icon = "user"
    menu_order = 140
