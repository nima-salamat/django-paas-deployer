from __future__ import annotations

from rest_framework.permissions import BasePermission


def _has_rule(user, code: str) -> bool:
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


class HasInviteManageRule(BasePermission):
    def has_permission(self, request, view):
        return _has_rule(request.user, "invites.manage")


class HasAuthCodesViewRule(BasePermission):
    def has_permission(self, request, view):
        return _has_rule(request.user, "auth_codes.view") or _has_rule(
            request.user, "auth_codes.manage"
        )


class HasAuthCodesManageRule(BasePermission):
    def has_permission(self, request, view):
        return _has_rule(request.user, "auth_codes.manage")
