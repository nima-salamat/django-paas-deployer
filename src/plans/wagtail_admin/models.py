"""Wagtail admin (snippet) registration for the plans app."""
from __future__ import annotations

from django.utils.translation import gettext_lazy as _

from cms.wagtail_admin.utils import panels_for
from plans.models import Plan
from wagtail.permission_policies.base import ModelPermissionPolicy
from wagtail.snippets.views.snippets import SnippetViewSet, SnippetViewSetGroup


def _user_has_rule(user, code: str) -> bool:
    if not user or not getattr(user, "is_authenticated", False):
        return False
    if getattr(user, "is_superuser", False):
        return True
    if not getattr(user, "is_staff", False):
        return False
    try:
        return code in list(user.rule.rules or [])
    except Exception:
        return False


class PlansPermissionPolicy(ModelPermissionPolicy):
    """Map the product's Plan rules onto Wagtail snippet permissions."""

    def user_has_permission(self, user, action):
        if action in {"view", "inspect"}:
            return _user_has_rule(user, "plans.view") or _user_has_rule(user, "plans.manage")
        if action in {"add", "change", "delete"}:
            return _user_has_rule(user, "plans.manage")
        return super().user_has_permission(user, action)

    def user_has_any_permission(self, user, actions):
        return any(self.user_has_permission(user, action) for action in actions)


class PlanViewSet(SnippetViewSet):
    model = Plan
    permission_policy = PlansPermissionPolicy(Plan)
    icon = "doc-full-inverse"
    menu_label = _("Resource plans")
    menu_order = 100
    list_display = [
        "name",
        "platform",
        "plan_type",
        "max_cpu",
        "max_ram",
        "max_storage",
        "price_per_hour",
        "log_retention_days",
        "log_storage_mb",
        "persistent_logging",
        "realtime_logging",
        "created_at",
    ]
    list_filter = [
        "platform",
        "plan_type",
        "storage_type",
        "name",
        "persistent_logging",
        "realtime_logging",
        "log_quota_behavior",
    ]
    search_fields = ["name", "platform", "log_quota_behavior"]
    ordering = ["name", "platform"]
    list_per_page = 50
    panels = panels_for(
        editable=[
            "name",
            "platform",
            "plan_type",
            "max_cpu",
            "max_ram",
            "max_storage",
            "price_per_hour",
            "storage_type",
            "log_retention_days",
            "log_storage_mb",
            "log_ingest_bytes_per_sec",
            "persistent_logging",
            "realtime_logging",
            "log_quota_behavior",
        ],
        read_only=["id", "created_at", "updated_at"],
    )


class PlansGroup(SnippetViewSetGroup):
    items = (PlanViewSet,)
    menu_label = _("Resource plans")
    menu_icon = "doc-full-inverse"
    menu_order = 100
