"""Admin panel APIs: users, rules/permissions (Django-admin style in React).

Permission model
----------------
* Superuser bypasses everything.
* Staff with `users.view`         → list/get users.
* Staff with `users.create`       → create users (NO rule assignment, NO staff/superuser flag toggle).
* Staff with `users.manage`       → update users, assign rules, deactivate, delete (soft).
* Staff with `users.manage_rules` → ONLY edit the `rules` array of other users
                                    (cannot change email/password/staff/superuser).
                                    Useful for helpdesk-style staff who should
                                    fine-tune permissions but not touch identity fields.
* Staff with `tables.view`        → browse registered Django tables (read-only).
* Staff with `tables.manage`      → also delete rows from deletable tables.

New permission codes
--------------------
* ``users.create`` — allows creating users without granting ``users.manage``.
* ``users.manage_rules`` — allows editing only the rules array of other users.
  Cannot be combined to escalate: a user with only ``users.manage_rules`` cannot
  grant permissions they do not own (defense-in-depth).
* ``tables.view`` / ``tables.manage`` — DB tables browser (see admin_tables_api).
"""
from __future__ import annotations

from django.contrib.auth import get_user_model
from django.db.models import Q
from django.utils.translation import gettext as _
from rest_framework import status
from rest_framework.pagination import PageNumberPagination
from rest_framework.permissions import BasePermission, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.authentication import JWTAuthentication

from .models import Rule, Profile

User = get_user_model()

# Canonical permission codes stored in Rule.rules (ArrayField)
KNOWN_PERMISSIONS = [
    # Tickets
    "tickets.view",
    "tickets.manage",
    "tickets.delete",
    # Users
    "users.view",
    "users.create",         # limited create (no rules, no flags)
    "users.manage",         # full manage: rules, staff flag, superuser flag (only superuser)
    "users.manage_rules",   # ONLY edit rules of others (no identity fields)
    # Invites & auth codes
    "invites.manage",
    "auth_codes.view",
    "auth_codes.manage",
    # Emails & departments
    "emails.manage",
    "departments.manage",
    # Services stack
    "services.view",
    "services.manage",
    "services.delete",
    "deploys.manage",
    "volumes.manage",
    "networks.manage",
    # Plans
    "plans.view",
    "plans.manage",
    # Login system
    "login_settings.view",
    "login_settings.manage",
    # DB tables browser (NEW)
    "tables.view",
    "tables.manage",
]


def ok(msg="ok", data=None, http_status=status.HTTP_200_OK):
    body = {"success": True, "message": msg}
    if data is not None:
        body["data"] = data
    return Response(body, status=http_status)


def err(msg, http_status=status.HTTP_400_BAD_REQUEST, extra=None):
    body = {"success": False, "message": msg}
    if extra:
        body.update(extra)
    return Response(body, status=http_status)


def user_rules(user) -> list:
    try:
        return list(user.rule.rules or [])
    except Exception:
        return []


def user_has_rule(user, code: str) -> bool:
    if not user or not user.is_authenticated:
        return False
    if user.is_superuser:
        return True
    return code in user_rules(user)


class IsSuperuser(BasePermission):
    def has_permission(self, request, view):
        return bool(request.user and request.user.is_authenticated and request.user.is_superuser)


class HasAdminRule(BasePermission):
    """Require superuser OR is_staff with a specific rule code (view.required_rule)."""

    def has_permission(self, request, view):
        u = request.user
        if not u or not u.is_authenticated:
            return False
        if u.is_superuser:
            return True
        if not u.is_staff:
            return False
        required = getattr(view, "required_rule", None)
        if not required:
            return True
        return user_has_rule(u, required)


class AdminPagination(PageNumberPagination):
    page_size = 20
    page_size_query_param = "page_size"
    max_page_size = 100


def serialize_user(u: User, include_rules=True) -> dict:
    data = {
        "id": u.id,
        "uuid": getattr(u, "uuid", None),
        "username": u.username,
        "email": u.email,
        "phone_number": str(u.phone_number) if u.phone_number else None,
        "email_verified": bool(getattr(u, "email_verified", False)),
        "phone_number_verified": bool(getattr(u, "phone_number_verified", False)),
        "is_staff": bool(u.is_staff),
        "is_superuser": bool(u.is_superuser),
        "is_active": bool(u.is_active),
        "date_joined": u.date_joined.isoformat() if u.date_joined else None,
        "balance": str(getattr(u, "balance", "0")),
    }
    # Profile images (ordered by `order` then id)
    try:
        profiles = list(
            Profile.objects.filter(user=u).order_by("order", "id")
        )
        data["profiles"] = [
            {
                "id": p.id,
                "order": p.order,
                "image": p.image.url if p.image else None,
                "created_at": p.created_at.isoformat() if p.created_at else None,
            }
            for p in profiles
        ]
    except Exception:
        data["profiles"] = []
    if include_rules:
        data["rules"] = user_rules(u)
    return data


class AdminPermissionCatalogAPIView(APIView):
    """List known permission codes for the UI."""
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAuthenticated, HasAdminRule]
    required_rule = "users.view"

    def get(self, request):
        if not (
            request.user.is_superuser
            or user_has_rule(request.user, "users.view")
            or user_has_rule(request.user, "users.manage")
        ):
            if not request.user.is_superuser:
                return err("Forbidden", status.HTTP_403_FORBIDDEN)
        return ok(data={"permissions": KNOWN_PERMISSIONS})


class AdminUserListAPIView(APIView):
    """
    GET  /api/users/admin/users/?search=&is_staff=&is_active=&page=
    POST /api/users/admin/users/  create minimal user.

    Permission matrix for POST:
      * superuser                              → can set is_staff / is_superuser / rules
      * staff with users.manage                → can set is_staff (but not is_superuser) and rules
      * staff with users.create (no manage)    → can ONLY create a basic user (no rules,
                                                 no staff flag, no superuser flag, active=True)
    """
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAuthenticated, HasAdminRule]
    required_rule = "users.view"

    def get(self, request):
        from core.app_cache import (
            cache_get, cache_set, user_admin_list_key, USER_ADMIN_TTL, USER_ADMIN_LIMIT,
        )
        u = request.user
        allowed = (
            u.is_superuser
            or user_has_rule(u, "users.view")
            or user_has_rule(u, "users.manage")
            or user_has_rule(u, "users.create")
            or u.is_staff  # staff can list; edit still gated
        )
        if not allowed:
            return err("Forbidden", status.HTTP_403_FORBIDDEN)

        params = {k: request.query_params.get(k) or "" for k in ("search", "is_staff", "is_active", "is_superuser", "page", "page_size")}
        key = user_admin_list_key(params)
        try:
            cached = cache_get(key)
            if cached is not None:
                return Response(cached)
        except Exception:
            pass

        qs = User.objects.all().order_by("-date_joined")
        search = (params.get("search") or "").strip()
        if search:
            qs = qs.filter(
                Q(username__icontains=search)
                | Q(email__icontains=search)
                | Q(phone_number__icontains=search)
            )
        if params.get("is_staff") in ("1", "true", "True"):
            qs = qs.filter(is_staff=True)
        elif params.get("is_staff") in ("0", "false", "False"):
            qs = qs.filter(is_staff=False)
        if params.get("is_active") in ("1", "true", "True"):
            qs = qs.filter(is_active=True)
        elif params.get("is_active") in ("0", "false", "False"):
            qs = qs.filter(is_active=False)
        if params.get("is_superuser") in ("1", "true"):
            qs = qs.filter(is_superuser=True)

        paginator = AdminPagination()
        page = paginator.paginate_queryset(qs, request)
        user_ids = [x.id for x in page]
        rules_map = {
            r.user_id: list(r.rules or [])
            for r in Rule.objects.filter(user_id__in=user_ids)
        }
        results = []
        for x in page:
            d = serialize_user(x, include_rules=False)
            d["rules"] = rules_map.get(x.id, [])
            results.append(d)
        resp = paginator.get_paginated_response(results)
        try:
            cache_set(key, resp.data, USER_ADMIN_TTL)
        except Exception:
            pass
        return resp

    def post(self, request):
        u = request.user
        is_su = bool(u.is_superuser)
        can_manage = is_su or user_has_rule(u, "users.manage")
        can_create = can_manage or user_has_rule(u, "users.create")
        if not can_create:
            return err("Missing permission users.create or users.manage", status.HTTP_403_FORBIDDEN)

        username = (request.data.get("username") or "").strip()
        email = (request.data.get("email") or "").strip() or None
        if not username:
            return err("username is required")
        if User.objects.filter(username=username).exists():
            return err("username already exists")
        if email and User.objects.filter(email=email).exists():
            return err("email already exists")

        u_new = User(username=username, email=email)
        password = request.data.get("password")
        if password:
            u_new.set_password(password)
        u_new.is_active = bool(request.data.get("is_active", True))

        # Limited staff without users.manage cannot set is_staff / is_superuser / rules
        if can_manage:
            u_new.is_staff = bool(request.data.get("is_staff", False))
            # never allow creating superuser via this unless requester is superuser
            if is_su and request.data.get("is_superuser"):
                u_new.is_superuser = True
                u_new.is_staff = True
        else:
            # users.create-only: force flags off
            u_new.is_staff = False
            u_new.is_superuser = False

        u_new.save()
        try:
            from core.app_cache import invalidate_all_users_admin
            invalidate_all_users_admin()
        except Exception:
            pass

        if can_manage:
            rules = request.data.get("rules")
            if isinstance(rules, list):
                clean = [r for r in rules if r in KNOWN_PERMISSIONS]
                Rule.objects.update_or_create(user=u_new, defaults={"rules": clean})
        return ok(
            "User created",
            data=serialize_user(u_new),
            http_status=status.HTTP_201_CREATED,
        )


class AdminUserDetailAPIView(APIView):
    """
    GET    /api/users/admin/users/<pk>/
    PATCH  /api/users/admin/users/<pk>/
    DELETE /api/users/admin/users/<pk>/  (soft-delete; hard with ?hard=1 superuser only)
    """
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAuthenticated, HasAdminRule]
    required_rule = "users.view"

    def _get(self, pk):
        return User.objects.get(pk=pk)

    def get(self, request, pk):
        if not (
            request.user.is_superuser
            or user_has_rule(request.user, "users.view")
            or user_has_rule(request.user, "users.manage")
            or user_has_rule(request.user, "users.create")
        ):
            return err("Forbidden", status.HTTP_403_FORBIDDEN)
        try:
            u = self._get(pk)
        except User.DoesNotExist:
            return err("Not found", status.HTTP_404_NOT_FOUND)
        return ok(data=serialize_user(u))

    def patch(self, request, pk):
        u_req = request.user
        is_su = bool(u_req.is_superuser)
        can_manage = is_su or user_has_rule(u_req, "users.manage")
        can_create = can_manage or user_has_rule(u_req, "users.create")
        can_manage_rules = is_su or user_has_rule(u_req, "users.manage_rules")
        if not (can_create or can_manage_rules):
            return err(
                "Missing permission users.create, users.manage, or users.manage_rules",
                status.HTTP_403_FORBIDDEN,
            )

        try:
            u = self._get(pk)
        except User.DoesNotExist:
            return err("Not found", status.HTTP_404_NOT_FOUND)

        # Protect last superuser / self-demotion edge cases
        if u.is_superuser and not is_su:
            return err("Only superuser can edit another superuser", status.HTTP_403_FORBIDDEN)

        data = request.data

        # ─── users.manage_rules path — ONLY rules can be edited ───────────────
        # If the caller has manage_rules but NOT users.create/users.manage, they
        # can ONLY touch the rules array. Any other field in the payload is
        # rejected with 403 to prevent privilege escalation.
        if can_manage_rules and not can_create:
            if "rules" not in data:
                return err(
                    "With users.manage_rules only you may only edit the rules array.",
                    status.HTTP_403_FORBIDDEN,
                )
            extra_keys = set(data.keys()) - {"rules"}
            if extra_keys:
                return err(
                    f"With users.manage_rules only you may not change: {sorted(extra_keys)}",
                    status.HTTP_403_FORBIDDEN,
                )
            # Defense-in-depth: never let a non-superuser grant permissions they don't have.
            requested = set(data["rules"])
            allowed_to_grant = set(KNOWN_PERMISSIONS) if is_su else set(user_rules(u_req))
            forbidden = requested - allowed_to_grant
            if forbidden:
                return err(
                    "You cannot grant permissions you do not own.",
                    status.HTTP_403_FORBIDDEN,
                    extra={"forbidden": sorted(forbidden)},
                )
            clean = [r for r in data["rules"] if r in KNOWN_PERMISSIONS]
            Rule.objects.update_or_create(user=u, defaults={"rules": clean})
            return ok("Rules updated", data=serialize_user(u))

        # ─── Normal path (users.create / users.manage) ────────────────────────

        # ---- Fields everyone with users.create OR users.manage can edit ----
        if "email" in data:
            u.email = (data.get("email") or "").strip() or None
        if "phone_number" in data:
            u.phone_number = (data.get("phone_number") or "").strip() or None
        if "password" in data:
            if data.get("password"):
                u.set_password(data["password"])

        # ---- Staff flag: requires users.manage (NOT users.create) ----
        if "is_staff" in data:
            if not can_manage:
                return err("Missing permission users.manage to change staff flag", status.HTTP_403_FORBIDDEN)
            if u.id == u_req.id and not data.get("is_staff"):
                return err("Cannot remove your own staff flag")
            u.is_staff = bool(data.get("is_staff"))

        # ---- Active flag: requires users.manage OR users.create ----
        if "is_active" in data:
            if u.id == u_req.id and not data.get("is_active"):
                return err("Cannot deactivate yourself")
            u.is_active = bool(data.get("is_active"))

        # ---- Superuser flag: superuser only ----
        if "is_superuser" in data and is_su:
            if u.id == u_req.id and not data.get("is_superuser"):
                return err("Cannot remove your own superuser flag")
            u.is_superuser = bool(data.get("is_superuser"))
            if u.is_superuser:
                u.is_staff = True
        elif "is_superuser" in data and not is_su:
            return err("Only superuser can change superuser flag", status.HTTP_403_FORBIDDEN)

        u.save()

        # ---- Rules: requires users.manage OR users.manage_rules ----
        if "rules" in data and isinstance(data["rules"], list):
            if not (can_manage or can_manage_rules):
                return err(
                    "Missing permission users.manage or users.manage_rules to update rules",
                    status.HTTP_403_FORBIDDEN,
                )
            # Defense-in-depth: never let a non-superuser grant permissions they don't have.
            requested = set(data["rules"])
            allowed_to_grant = set(KNOWN_PERMISSIONS) if is_su else set(user_rules(u_req))
            forbidden = requested - allowed_to_grant
            if forbidden:
                return err(
                    "You cannot grant permissions you do not own.",
                    status.HTTP_403_FORBIDDEN,
                    extra={"forbidden": sorted(forbidden)},
                )
            clean = [r for r in data["rules"] if r in KNOWN_PERMISSIONS]
            Rule.objects.update_or_create(user=u, defaults={"rules": clean})

        return ok("Updated", data=serialize_user(u))

    def delete(self, request, pk):
        """Soft-delete: deactivate account (hard delete only for superuser with ?hard=1)."""
        u_req = request.user
        is_su = bool(u_req.is_superuser)
        can_manage = is_su or user_has_rule(u_req, "users.manage")
        can_create = can_manage or user_has_rule(u_req, "users.create")
        # delete requires users.manage (not just users.create) — destructive op
        if not can_manage:
            return err("Missing permission users.manage to delete a user", status.HTTP_403_FORBIDDEN)
        try:
            u = self._get(pk)
        except User.DoesNotExist:
            return err("Not found", status.HTTP_404_NOT_FOUND)
        if u.id == u_req.id:
            return err("Cannot delete yourself")
        if u.is_superuser and not is_su:
            return err("Forbidden", status.HTTP_403_FORBIDDEN)
        hard = request.query_params.get("hard") in ("1", "true")
        if hard and is_su:
            u.delete()
            return ok("User permanently deleted")
        u.is_active = False
        u.save(update_fields=["is_active"])
        return ok("User deactivated")


class AdminUserRulesAPIView(APIView):
    """PUT rules for a user. Requires users.manage (NOT users.create)."""
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAuthenticated, HasAdminRule]
    required_rule = "users.manage"

    def put(self, request, pk):
        u_req = request.user
        is_su = bool(u_req.is_superuser)
        if not (is_su or user_has_rule(u_req, "users.manage")):
            return err("Missing permission users.manage", status.HTTP_403_FORBIDDEN)
        try:
            u = User.objects.get(pk=pk)
        except User.DoesNotExist:
            return err("Not found", status.HTTP_404_NOT_FOUND)
        rules = request.data.get("rules")
        if not isinstance(rules, list):
            return err("rules must be a list")
        requested = set(rules)
        allowed_to_grant = set(KNOWN_PERMISSIONS) if is_su else set(user_rules(u_req))
        forbidden = requested - allowed_to_grant
        if forbidden:
            return err(
                "You cannot grant permissions you do not own.",
                status.HTTP_403_FORBIDDEN,
                extra={"forbidden": sorted(forbidden)},
            )
        clean = [r for r in rules if r in KNOWN_PERMISSIONS]
        Rule.objects.update_or_create(user=u, defaults={"rules": clean})
        return ok("Rules updated", data={"rules": clean})


class MePermissionsAPIView(APIView):
    """
    GET /api/users/admin/me/permissions/
    Current staff identity + effective rules for the React admin shell.
    Any authenticated staff (or superuser) can call this.
    """
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAuthenticated]

    def get(self, request):
        u = request.user
        if not (u.is_staff or u.is_superuser):
            return err("Staff only", status.HTTP_403_FORBIDDEN)
        rules = list(KNOWN_PERMISSIONS) if u.is_superuser else user_rules(u)
        return ok(
            data={
                "id": u.id,
                "username": u.username,
                "email": getattr(u, "email", None),
                "is_staff": bool(u.is_staff),
                "is_superuser": bool(u.is_superuser),
                "is_active": bool(u.is_active),
                "rules": rules,
                "all_permissions": KNOWN_PERMISSIONS,
                "profiles": [
                    {
                        "id": p.id,
                        "order": p.order,
                        "image": p.image.url if p.image else None,
                        "created_at": p.created_at.isoformat() if p.created_at else None,
                    }
                    for p in Profile.objects.filter(user=u).order_by("order", "id")
                ],
            }
        )


# ---------------------------------------------------------------------------
# Admin Profile image management
# ---------------------------------------------------------------------------
# Endpoints (mounted under /api/users/admin/users/<pk>/profiles/...):
#
#   GET    /api/users/admin/users/<pk>/profiles/                  → list profiles
#   POST   /api/users/admin/users/<pk>/profiles/                  → upload new image
#   PATCH  /api/users/admin/users/<pk>/profiles/<profile_id>/     → update order
#   DELETE /api/users/admin/users/<pk>/profiles/<profile_id>/     → delete image
#   POST   /api/users/admin/users/<pk>/profiles/reorder/          → bulk reorder
#                                                                  body: {orders: [{id, order}]}
#
# Permission:
#   * superuser                       → everything
#   * users.manage                    → everything
#   * users.create                    → everything (basic create/manage staff can edit photos)
#   * users.manage_rules              → NO access (rules-only permission)
#   * otherwise                       → 403
#
# Notes:
#   * Profile model enforces max 5 images per user via full_clean().
#   * Image is validated by ImageValidator(size_kb=2048, max_w=2560, max_h=1440).
#   * Deleting the last image is allowed (user just has no profile picture).


class _AdminProfilePermission(BasePermission):
    """Allows superuser / users.manage / users.create. NOT users.manage_rules."""

    def has_permission(self, request, view):
        u = request.user
        if not u or not u.is_authenticated:
            return False
        if u.is_superuser:
            return True
        if not u.is_staff:
            return False
        return (
            user_has_rule(u, "users.manage")
            or user_has_rule(u, "users.create")
        )


def _serialize_profile(p: Profile) -> dict:
    return {
        "id": p.id,
        "order": p.order,
        "image": p.image.url if p.image else None,
        "created_at": p.created_at.isoformat() if p.created_at else None,
    }


class AdminProfileListCreateAPIView(APIView):
    """
    GET  /api/users/admin/users/<pk>/profiles/    → list user's profile images
    POST /api/users/admin/users/<pk>/profiles/    → upload a new profile image
    """
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAuthenticated, _AdminProfilePermission]

    def get(self, request, pk):
        try:
            u = User.objects.get(pk=pk)
        except User.DoesNotExist:
            return err("User not found", status.HTTP_404_NOT_FOUND)
        qs = Profile.objects.filter(user=u).order_by("order", "id")
        return ok(data={"profiles": [_serialize_profile(p) for p in qs], "count": qs.count()})

    def post(self, request, pk):
        try:
            u = User.objects.get(pk=pk)
        except User.DoesNotExist:
            return err("User not found", status.HTTP_404_NOT_FOUND)

        image = request.FILES.get("image")
        if not image:
            return err("image file is required")

        # Determine next order
        existing_max = (
            Profile.objects.filter(user=u).order_by("-order").values_list("order", flat=True).first()
            or 0
        )
        profile = Profile(user=u, image=image, order=existing_max + 1)
        try:
            profile.full_clean()
        except Exception as exc:
            return err(f"Validation failed: {exc}", status.HTTP_400_BAD_REQUEST)
        try:
            profile.save()
        except Exception as exc:
            return err(f"Save failed: {exc}", status.HTTP_400_BAD_REQUEST)
        return ok(
            "Profile image uploaded",
            data=_serialize_profile(profile),
            http_status=status.HTTP_201_CREATED,
        )


class AdminProfileDetailAPIView(APIView):
    """
    PATCH  /api/users/admin/users/<pk>/profiles/<profile_id>/   → update order
    DELETE /api/users/admin/users/<pk>/profiles/<profile_id>/   → delete image
    """
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAuthenticated, _AdminProfilePermission]

    def _get(self, pk, profile_id):
        try:
            u = User.objects.get(pk=pk)
        except User.DoesNotExist:
            return None, err("User not found", status.HTTP_404_NOT_FOUND)
        try:
            return Profile.objects.get(pk=profile_id, user=u), None
        except Profile.DoesNotExist:
            return None, err("Profile image not found", status.HTTP_404_NOT_FOUND)

    def patch(self, request, pk, profile_id):
        profile, error = self._get(pk, profile_id)
        if error:
            return error
        new_order = request.data.get("order")
        if new_order is None:
            return err("order is required")
        try:
            new_order = int(new_order)
        except (TypeError, ValueError):
            return err("order must be an integer")
        profile.order = new_order
        profile.save(update_fields=["order"])
        return ok("Order updated", data=_serialize_profile(profile))

    def delete(self, request, pk, profile_id):
        profile, error = self._get(pk, profile_id)
        if error:
            return error
        try:
            profile.delete()
        except Exception as exc:
            return err(f"Delete failed: {exc}", status.HTTP_400_BAD_REQUEST)
        return ok("Profile image deleted")


class AdminProfileReorderAPIView(APIView):
    """
    POST /api/users/admin/users/<pk>/profiles/reorder/
    Body: {orders: [{id: int, order: int}, ...]}

    Bulk-reorders all profile images for the user in one transaction.
    """
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAuthenticated, _AdminProfilePermission]

    def post(self, request, pk):
        try:
            u = User.objects.get(pk=pk)
        except User.DoesNotExist:
            return err("User not found", status.HTTP_404_NOT_FOUND)

        orders = request.data.get("orders")
        if not isinstance(orders, list):
            return err("orders must be a list of {id, order}")

        from django.db import transaction
        try:
            with transaction.atomic():
                for entry in orders:
                    if not isinstance(entry, dict):
                        continue
                    pid = entry.get("id")
                    new_order = entry.get("order")
                    if pid is None or new_order is None:
                        continue
                    try:
                        pid = int(pid)
                        new_order = int(new_order)
                    except (TypeError, ValueError):
                        continue
                    Profile.objects.filter(pk=pid, user=u).update(order=new_order)
        except Exception as exc:
            return err(f"Reorder failed: {exc}", status.HTTP_400_BAD_REQUEST)

        qs = Profile.objects.filter(user=u).order_by("order", "id")
        return ok("Reordered", data={"profiles": [_serialize_profile(p) for p in qs]})
