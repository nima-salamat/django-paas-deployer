"""
Admin panel: read-only Django tables browser (with safe row delete + FK search).

Security model
--------------
* `tables.view`   — list registered models + read rows (paginated, filtered).
* `tables.manage` — also delete individual rows from the allowed models.

Only models explicitly registered in TABLE_REGISTRY can be queried.
Sensitive fields (password / token / secret) are masked on read.
Hard delete is restricted to models whose `deletable=True`.

Endpoints (mounted under /api/users/admin/tables/ in api_urls.py):

    GET  tables/                                       → list of registered models + schema
    GET  tables/<model_key>/?page=&q=                  → paginated rows
    GET  tables/<model_key>/<pk>/                      → single row
    DELETE tables/<model_key>/<pk>/                    → soft/hard delete (only if deletable)
    GET  tables/<model_key>/fk-search/?q=&field=&limit=→ search rows of a registered table
                                                          for FK picker autocomplete.
                                                          Returns [{pk, str}, ...].
"""
from __future__ import annotations

from typing import Dict, List, Tuple

from django.apps import apps as django_apps
from django.contrib.auth import get_user_model
from django.core.paginator import Paginator, EmptyPage, PageNotAnInteger
from django.db import models, transaction
from django.utils.translation import gettext as _
from rest_framework import status
from rest_framework.permissions import IsAuthenticated, BasePermission
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.authentication import JWTAuthentication

User = get_user_model()


# ---------------------------------------------------------------------------
# Permission helpers (mirror users.admin_apis)
# ---------------------------------------------------------------------------
def _user_rules(user) -> list:
    try:
        return list(user.rule.rules or [])
    except Exception:
        return []


def _user_has_rule(user, code: str) -> bool:
    if not user or not getattr(user, "is_authenticated", False):
        return False
    if getattr(user, "is_superuser", False):
        return True
    return code in _user_rules(user)


def _can_view_tables(user) -> bool:
    if not user or not user.is_authenticated:
        return False
    if user.is_superuser:
        return True
    if not user.is_staff:
        return False
    return _user_has_rule(user, "tables.view") or _user_has_rule(user, "tables.manage")


def _can_manage_tables(user) -> bool:
    if not user or not user.is_authenticated:
        return False
    if user.is_superuser:
        return True
    if not user.is_staff:
        return False
    return _user_has_rule(user, "tables.manage")


# ---------------------------------------------------------------------------
# Model registry
# ---------------------------------------------------------------------------
# Each entry: "<app_label>.<ModelName>" → config dict.
# Allowed keys: deletable, sensitive_fields, search_fields, exclude_fields,
#               per_page (int), label (str).
# WARNING: register models carefully. Treat every model as exposed to staff.
# Never register auth User directly without filtering sensitive columns —
# we handle that explicitly below.
TABLE_REGISTRY: Dict[str, dict] = {
    # ---- Users / auth ----
    "users.User": {
        "label": "Users",
        "deletable": False,           # never hard delete users here (use the user admin API)
        "sensitive_fields": {"password"},
        "search_fields": ["username", "email"],
        "exclude_fields": {"password"},
        "per_page": 25,
    },
    "users.Rule": {
        "label": "Permission rules",
        "deletable": False,
        "search_fields": ["user__username"],
        "per_page": 25,
    },
    "users.Profile": {
        "label": "Profile images",
        "deletable": True,
        "search_fields": ["user__username"],
        "per_page": 25,
    },
    "users.Receipt": {
        "label": "Receipts / payments",
        "deletable": False,
        "search_fields": ["user__username"],
        "per_page": 25,
    },

    # ---- Auth (login / codes / invites / settings) ----
    "auth_users.LoginSettings": {
        "label": "Login settings (singleton)",
        "deletable": False,
        "per_page": 5,
    },
    "auth_users.AuthCode": {
        "label": "Auth codes (OTP)",
        "deletable": True,
        "search_fields": ["user__username", "contact", "code"],
        "per_page": 25,
    },
    "auth_users.Invite": {
        "label": "Invites",
        "deletable": True,
        "search_fields": ["label", "token"],
        "sensitive_fields": {"token"} if False else set(),
        "per_page": 25,
    },

    # ---- Tickets ----
    "tickets.Ticket": {
        "label": "Tickets",
        "deletable": True,
        "search_fields": ["public_id", "subject", "user__username"],
        "per_page": 25,
    },
    "tickets.TicketMessage": {
        "label": "Ticket messages",
        "deletable": True,
        "search_fields": ["body"],
        "per_page": 25,
    },
    "tickets.TicketAttachment": {
        "label": "Ticket attachments",
        "deletable": True,
        "per_page": 25,
    },
    "tickets.Department": {
        "label": "Departments",
        "deletable": False,           # deactivated, not deleted
        "search_fields": ["name", "slug"],
        "per_page": 25,
    },
    "tickets.DepartmentMembership": {
        "label": "Department memberships",
        "deletable": True,
        "per_page": 25,
    },

    # ---- Plans ----
    "plans.Plan": {
        "label": "Plans",
        "deletable": True,
        "search_fields": ["name", "platform"],
        "per_page": 25,
    },

    # ---- Services / volumes / networks ----
    "services.Service": {
        "label": "Services",
        "deletable": False,           # use the service admin API (proper teardown)
        "search_fields": ["name", "user__username"],
        "per_page": 25,
    },
    "services.Volume": {
        "label": "Volumes",
        "deletable": True,
        "search_fields": ["name", "user__username"],
        "per_page": 25,
    },
    "services.PrivateNetwork": {
        "label": "Private networks",
        "deletable": True,
        "search_fields": ["name", "user__username"],
        "per_page": 25,
    },

    # ---- Deploy ----
    "deploy.Deploy": {
        "label": "Deploys",
        "deletable": True,
        "search_fields": ["name", "service__name"],
        "per_page": 25,
    },
    "deploy.DeployLog": {
        "label": "Deploy logs",
        "deletable": True,
        "per_page": 50,
    },
    "deploy.DeploymentState": {
        "label": "Deployment states",
        "deletable": False,
        "per_page": 25,
    },

    # ---- Emails ----
    "custom_emails.EmailTemplate": {
        "label": "Email templates",
        "deletable": True,
        "search_fields": ["name", "code"],
        "per_page": 25,
    },
    "custom_emails.EmailLog": {
        "label": "Email logs",
        "deletable": True,
        "search_fields": ["to_address", "subject"],
        "per_page": 50,
    },

    # ---- Core ----
    "core.SiteSetting": {
        "label": "Site settings (singleton)",
        "deletable": False,
        "per_page": 5,
    },
}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
SENSITIVE_FIELD_NAMES = {
    "password", "secret", "token", "api_key", "apikey", "access",
    "refresh", "private_key", "privatekey",
}


def _resolve_model(model_key: str):
    """'users.User' → Model class. Returns None if missing."""
    if "." not in model_key:
        return None
    app_label, model_name = model_key.split(".", 1)
    try:
        return django_apps.get_model(app_label, model_name)
    except LookupError:
        return None


def _field_schema(field) -> dict:
    ftype = type(field).__name__
    info = {
        "name": field.name,
        "type": ftype,
        "nullable": getattr(field, "null", False) or getattr(field, "blank", False),
        "editable": getattr(field, "editable", True),
        "is_relation": field.is_relation,
    }
    if field.is_relation:
        info["related"] = (
            f"{field.related_model._meta.app_label}."
            f"{field.related_model._meta.object_name}"
        )
        info["relation"] = (
            "many-to-many" if field.many_to_many
            else "one-to-many" if field.one_to_many
            else "one-to-one" if field.one_to_one
            else "many-to-one"
        )
    if field.choices:
        info["choices"] = [{"value": v, "label": str(l)} for v, l in field.choices]
    return info


def _is_sensitive(field, cfg) -> bool:
    name = (field.name or "").lower()
    if name in (cfg.get("sensitive_fields") or set()):
        return True
    return name in SENSITIVE_FIELD_NAMES


def _serialize_value(value):
    """JSON-safe conversion for arbitrary field values."""
    import datetime
    import decimal
    import uuid

    if value is None:
        return None
    if isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, decimal.Decimal):
        return str(value)
    if isinstance(value, (datetime.datetime, datetime.date, datetime.time)):
        return value.isoformat()
    if isinstance(value, uuid.UUID):
        return str(value)
    if isinstance(value, (list, tuple, set)):
        return [_serialize_value(v) for v in value]
    if hasattr(value, "isoformat"):
        try:
            return value.isoformat()
        except Exception:
            pass
    # FK / relation → pk + str
    try:
        return {"pk": value.pk, "str": str(value)}
    except AttributeError:
        pass
    return str(value)


def _serialize_row(instance, cfg) -> dict:
    """Serialize a model instance to a JSON-safe dict. Masks sensitive fields."""
    data = {}
    for field in instance._meta.get_fields():
        if field.name in (cfg.get("exclude_fields") or set()):
            continue
        try:
            if field.many_to_many or field.one_to_many:
                # Show pks only, don't trigger heavy queries
                data[field.name] = [
                    {"pk": r.pk, "str": str(r)} for r in getattr(instance, field.name).all()[:50]
                ]
                continue
            value = getattr(instance, field.name, None)
            if _is_sensitive(field, cfg):
                data[field.name] = "***REDACTED***" if value not in (None, "") else value
            else:
                data[field.name] = _serialize_value(value)
        except Exception as exc:
            data[field.name] = f"<error: {exc}>"
    return data


def _apply_search(qs, cfg, q):
    if not q or not cfg.get("search_fields"):
        return qs
    from django.db.models import Q
    q_obj = Q()
    for fname in cfg["search_fields"]:
        # Build nested lookup "__icontains"
        q_obj |= Q(**{f"{fname}__icontains": q})
    return qs.filter(q_obj)


def _get_table_config(model_key: str) -> Tuple[object, dict, str]:
    """Resolve (Model, config, error)."""
    cfg = TABLE_REGISTRY.get(model_key)
    if not cfg:
        return None, None, "Table not registered"
    Model = _resolve_model(model_key)
    if Model is None:
        return None, None, "Model not found"
    return Model, cfg, None


# ---------------------------------------------------------------------------
# Response helpers
# ---------------------------------------------------------------------------
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


# ---------------------------------------------------------------------------
# Permissions
# ---------------------------------------------------------------------------
class HasTablesViewRule(BasePermission):
    def has_permission(self, request, view):
        return _can_view_tables(request.user)


class HasTablesManageRule(BasePermission):
    def has_permission(self, request, view):
        return _can_manage_tables(request.user)


# ---------------------------------------------------------------------------
# Views
# ---------------------------------------------------------------------------
class AdminTableListView(APIView):
    """
    GET /api/users/admin/tables/
    Returns the catalog of registered tables + their field schema.
    """
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAuthenticated, HasTablesViewRule]

    def get(self, request):
        out = []
        for key, cfg in TABLE_REGISTRY.items():
            Model = _resolve_model(key)
            if Model is None:
                continue
            try:
                count = Model.objects.count()
            except Exception:
                count = None
            out.append({
                "key": key,
                "label": cfg.get("label") or Model._meta.verbose_name.title(),
                "app": Model._meta.app_label,
                "model": Model._meta.object_name,
                "count": count,
                "deletable": bool(cfg.get("deletable")),
                "searchable": bool(cfg.get("search_fields")),
                "per_page": int(cfg.get("per_page", 25)),
            })
        out.sort(key=lambda r: r["label"])
        return ok(data={"tables": out})


class AdminTableRowsView(APIView):
    """
    GET /api/users/admin/tables/<model_key>/?page=&q=
    Returns paginated rows for a registered table.
    """
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAuthenticated, HasTablesViewRule]

    def get(self, request, model_key):
        Model, cfg, error = _get_table_config(model_key)
        if error:
            return err(error, status.HTTP_404_NOT_FOUND)

        qs = Model.objects.all()
        # Default ordering: pk desc, fallback to id, fallback to first unique
        try:
            qs = qs.order_by("-id")
        except Exception:
            try:
                qs = qs.order_by("-pk")
            except Exception:
                pass

        q = (request.query_params.get("q") or "").strip()
        qs = _apply_search(qs, cfg, q)

        per_page = int(request.query_params.get("page_size") or cfg.get("per_page", 25))
        per_page = max(1, min(per_page, 100))
        page_num = int(request.query_params.get("page") or 1)

        paginator = Paginator(qs, per_page)
        try:
            page = paginator.page(page_num)
        except (EmptyPage, PageNotAnInteger):
            page = paginator.page(1)

        rows = [_serialize_row(obj, cfg) for obj in page.object_list]

        # Field schema (cached at request time)
        fields = []
        for f in Model._meta.get_fields():
            if f.name in (cfg.get("exclude_fields") or set()):
                continue
            try:
                fs = _field_schema(f)
                fs["sensitive"] = _is_sensitive(f, cfg)
                fields.append(fs)
            except Exception:
                continue

        return ok(data={
            "model_key": model_key,
            "label": cfg.get("label") or Model._meta.verbose_name.title(),
            "count": paginator.count,
            "page": page.number,
            "num_pages": paginator.num_pages,
            "per_page": per_page,
            "fields": fields,
            "rows": rows,
            "deletable": bool(cfg.get("deletable")),
        })


class AdminTableRowView(APIView):
    """
    GET    /api/users/admin/tables/<model_key>/<pk>/
    DELETE /api/users/admin/tables/<model_key>/<pk>/
    """
    authentication_classes = [JWTAuthentication]

    def get_permissions(self):
        if self.request.method == "DELETE":
            return [IsAuthenticated(), HasTablesManageRule()]
        return [IsAuthenticated(), HasTablesViewRule()]

    def _get_object(self, Model, pk):
        # Try numeric pk first, fallback to uuid (some models use uuid)
        try:
            return Model.objects.get(pk=pk)
        except (Model.DoesNotExist, ValueError, TypeError):
            try:
                return Model.objects.get(uuid=pk)
            except Exception:
                return None

    def get(self, request, model_key, pk):
        Model, cfg, error = _get_table_config(model_key)
        if error:
            return err(error, status.HTTP_404_NOT_FOUND)
        obj = self._get_object(Model, pk)
        if obj is None:
            return err("Row not found", status.HTTP_404_NOT_FOUND)
        return ok(data=_serialize_row(obj, cfg))

    def delete(self, request, model_key, pk):
        Model, cfg, error = _get_table_config(model_key)
        if error:
            return err(error, status.HTTP_404_NOT_FOUND)
        if not cfg.get("deletable"):
            return err(
                "This table is not deletable from the admin UI. Use the dedicated admin API instead.",
                status.HTTP_403_FORBIDDEN,
            )

        obj = self._get_object(Model, pk)
        if obj is None:
            return err("Row not found", status.HTTP_404_NOT_FOUND)

        # Safety: refuse to delete the last superuser
        if Model.__name__ == "User" and obj.is_superuser:
            from django.db.models import Count
            supers = User.objects.filter(is_superuser=True, is_active=True).count()
            if supers <= 1:
                return err(
                    "Refusing to delete the last active superuser.",
                    status.HTTP_400_BAD_REQUEST,
                )

        label = str(obj)
        try:
            with transaction.atomic():
                obj.delete()
        except models.ProtectedError as pe:
            return err(
                "Cannot delete: row is referenced by other rows.",
                status.HTTP_409_CONFLICT,
                extra={"protected": [str(o) for o in pe.protected_objects[:50]]},
            )
        except Exception as exc:
            return err(f"Delete failed: {exc}", status.HTTP_400_BAD_REQUEST)
        return ok(f"Deleted: {label}")


class AdminTableFKSearchAPIView(APIView):
    """
    GET /api/users/admin/tables/<model_key>/fk-search/?q=&field=&limit=

    Lightweight FK picker autocomplete. Searches any registered table by
    any of its registered `search_fields` (or a single `field` query param)
    and returns [{pk, str}, ...] — never full rows, never sensitive data.

    Used by TablesPanel's create/edit dialogs to let the admin pick a FK
    row by typing any field (e.g. username, email, name, public_id).

    Query params:
        q     : str   — search term (optional; empty → first N rows)
        field : str   — restrict search to a single field (optional)
        limit : int   — max results, default 25, hard cap 100
    """
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAuthenticated, HasTablesViewRule]

    def get(self, request, model_key):
        Model, cfg, error = _get_table_config(model_key)
        if error:
            return err(error, status.HTTP_404_NOT_FOUND)

        q = (request.query_params.get("q") or "").strip()
        field = (request.query_params.get("field") or "").strip()
        try:
            limit = int(request.query_params.get("limit") or 25)
        except (TypeError, ValueError):
            limit = 25
        limit = max(1, min(limit, 100))

        qs = Model.objects.all()

        if q:
            from django.db.models import Q

            if field:
                # Single-field search: validate field exists on the model
                valid_field_names = {f.name for f in Model._meta.get_fields()}
                if field in valid_field_names:
                    qs = qs.filter(**{f"{field}__icontains": q})
                # else: no filter — return empty
                else:
                    return ok(data={"results": [], "model_key": model_key})
            else:
                # Multi-field search across registered search_fields
                search_fields = cfg.get("search_fields") or []
                if search_fields:
                    q_obj = Q()
                    for fname in search_fields:
                        q_obj |= Q(**{f"{fname}__icontains": q})
                    qs = qs.filter(q_obj)
                else:
                    # Fallback: search across all string fields
                    q_obj = Q()
                    for f in Model._meta.get_fields():
                        if (
                            getattr(f, "editable", False)
                            and not getattr(f, "is_relation", False)
                            and not _is_sensitive(f, cfg)
                            and getattr(f, "max_length", None)
                            and f.name != "id"
                        ):
                            q_obj |= Q(**{f"{f.name}__icontains": q})
                    if q_obj:
                        qs = qs.filter(q_obj)

        # Ordering
        try:
            qs = qs.order_by("-id")
        except Exception:
            try:
                qs = qs.order_by("-pk")
            except Exception:
                pass

        qs = qs[:limit]

        # Build {pk, str} pairs — never expose sensitive fields
        results = []
        for obj in qs:
            results.append({"pk": obj.pk, "str": str(obj)[:200]})
        return ok(data={"results": results, "model_key": model_key, "count": len(results)})
