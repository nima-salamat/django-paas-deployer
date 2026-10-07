from __future__ import annotations

import ast
import importlib
import inspect
from pathlib import Path

from django.apps import apps
from django.urls import URLPattern, URLResolver
from rest_framework.permissions import AllowAny
from rest_framework.serializers import ModelSerializer

PROJECT_APP_LABELS = {
    "agent",
    "app_catalog",
    "auth_users",
    "cms",
    "core",
    "custom_emails",
    "deploy",
    "docs",
    "logs",
    "messenger",
    "plans",
    "services",
    "tickets",
    "users",
}

API_ROOT_PREFIXES = (
    "users/",
    "api/",
    "auth/",
    "plans/",
    "services/",
    "deploy/",
    "agent/",
)

SOURCE_ROOT = Path(__file__).resolve().parents[2]


def _walk_patterns(patterns, prefix=""):
    for pattern in patterns:
        if isinstance(pattern, URLResolver):
            route = str(pattern.pattern)
            yield from _walk_patterns(pattern.url_patterns, prefix + route)
        elif isinstance(pattern, URLPattern):
            yield prefix + str(pattern.pattern), pattern


def _drf_callback(pattern):
    callback = pattern.callback
    cls = getattr(callback, "cls", None)
    return callback, cls


def _is_project_api_route(route):
    normalized = route.lstrip("^")
    return normalized.startswith(API_ROOT_PREFIXES)


def test_every_project_model_is_discoverable():
    discovered = {
        model._meta.app_label
        for model in apps.get_models()
        if model._meta.app_label in PROJECT_APP_LABELS
        and not model._meta.abstract
        and not model._meta.proxy
    }
    assert discovered == PROJECT_APP_LABELS


def test_every_modelserializer_declares_a_real_model_and_valid_read_only_fields():
    failures = []

    for label in sorted(PROJECT_APP_LABELS):
        module_name = f"{label}.serializers"
        try:
            module = importlib.import_module(module_name)
        except ModuleNotFoundError as exc:
            if exc.name == module_name:
                continue
            raise

        for name, cls in inspect.getmembers(module, inspect.isclass):
            if cls is ModelSerializer:
                continue
            try:
                is_model_serializer = issubclass(cls, ModelSerializer)
            except TypeError:
                is_model_serializer = False
            if not is_model_serializer or cls.__module__ != module.__name__:
                continue

            meta = getattr(cls, "Meta", None)
            model = getattr(meta, "model", None) if meta else None
            if model is None:
                failures.append(f"{module_name}.{name}: missing Meta.model")
                continue

            try:
                serializer = cls()
                field_names = set(serializer.fields.keys())
            except Exception as exc:
                failures.append(f"{module_name}.{name}: fields failed: {exc}")
                continue

            meta_fields = getattr(meta, "fields", "__all__")
            if meta_fields != "__all__":
                missing = set(meta_fields) - field_names
                if missing:
                    failures.append(
                        f"{module_name}.{name}: Meta.fields missing from serializer: {sorted(missing)}"
                    )

            read_only = set(getattr(meta, "read_only_fields", ()) or ())
            missing_read_only = read_only - field_names
            if missing_read_only:
                failures.append(
                    f"{module_name}.{name}: read_only_fields missing: {sorted(missing_read_only)}"
                )

            if not model._meta.abstract:
                expected = apps.get_model(
                    model._meta.app_label,
                    model.__name__,
                )
                if expected is not model:
                    failures.append(
                        f"{module_name}.{name}: Meta.model is not the registered model"
                    )

    assert failures == [], "\n".join(failures)


def test_every_project_drf_endpoint_has_global_or_auth_rate_limit_policy():
    import config.urls as root_urls
    from core.throttling import (
        AuthenticationIPRateThrottle,
        GlobalIPRateThrottle,
    )

    configured = set(getattr(__import__("django.conf", fromlist=["settings"]).settings, "REST_FRAMEWORK", {}).get("DEFAULT_THROTTLE_CLASSES", ()))
    required_default = {
        "core.throttling.GlobalIPRateThrottle",
        "core.throttling.GlobalUserRateThrottle",
    }
    assert required_default.issubset(configured)

    missing = []
    acceptable_explicit = {GlobalIPRateThrottle, AuthenticationIPRateThrottle}

    for route, pattern in _walk_patterns(root_urls.urlpatterns):
        if not _is_project_api_route(route):
            continue
        _callback, cls = _drf_callback(pattern)
        if cls is None or "throttle_classes" not in cls.__dict__:
            continue

        classes = set(getattr(cls, "throttle_classes", ()) or ())
        if not classes.intersection(acceptable_explicit):
            name = pattern.name or "<unnamed>"
            missing.append(f"{name}: {route} -> {cls.__module__}.{cls.__name__}")

    assert missing == [], (
        "Explicitly throttled DRF endpoints must retain a client-IP boundary "
        "(global or authentication-specific):\n" + "\n".join(sorted(missing))
    )


def test_every_project_drf_endpoint_declares_an_explicit_permission_policy():
    import config.urls as root_urls

    missing = []
    for route, pattern in _walk_patterns(root_urls.urlpatterns):
        if not _is_project_api_route(route):
            continue
        callback, cls = _drf_callback(pattern)
        if cls is None:
            continue

        permissions = getattr(cls, "permission_classes", None)
        if permissions:
            continue

        name = pattern.name or "<unnamed>"
        missing.append(f"{name}: {route} -> {cls.__module__}.{cls.__name__}")

    assert missing == [], (
        "DRF endpoints rely on the framework AllowAny default instead of an "
        "explicit permission policy:\n" + "\n".join(sorted(missing))
    )


def test_protected_project_drf_endpoints_are_not_anonymous_only():
    import config.urls as root_urls

    violations = []
    for route, pattern in _walk_patterns(root_urls.urlpatterns):
        if not _is_project_api_route(route):
            continue
        _callback, cls = _drf_callback(pattern)
        if cls is None:
            continue

        permissions = list(getattr(cls, "permission_classes", ()) or ())
        if not permissions:
            continue
        if all(permission is AllowAny for permission in permissions):
            # Public views are valid only when the implementation explicitly
            # opts into AllowAny; this test catches accidental anonymous-only
            # access on non-public application routes.
            route_name = pattern.name or ""
            public_markers = (
                "login",
                "signup",
                "recovery",
                "password_recovery",
                "invite_validate",
                "platform_plans",
                "plans_api",
            )
            if not any(marker in route_name for marker in public_markers):
                violations.append(
                    f"{route_name}: {route} is AllowAny-only"
                )

    assert violations == [], "\n".join(sorted(violations))


def test_api_source_files_can_be_parsed_as_python():
    failures = []
    for path in SOURCE_ROOT.rglob("*.py"):
        if path.parts[-2:-1] and path.name in {"apis.py", "admin_apis.py", "serializers.py"}:
            try:
                ast.parse(path.read_text(encoding="utf-8"))
            except SyntaxError as exc:
                failures.append(f"{path}: {exc}")
    assert failures == [], "\n".join(failures)


def test_every_project_model_viewset_declares_queryset_and_serializer_contract():
    import config.urls as root_urls
    from rest_framework.viewsets import ModelViewSet

    failures = []
    seen = set()

    for route, pattern in _walk_patterns(root_urls.urlpatterns):
        if not _is_project_api_route(route):
            continue
        _callback, cls = _drf_callback(pattern)
        if cls is None or cls in seen:
            continue
        seen.add(cls)

        try:
            is_model_viewset = issubclass(cls, ModelViewSet)
        except TypeError:
            is_model_viewset = False
        if not is_model_viewset:
            continue

        serializer_class = getattr(cls, "serializer_class", None)
        has_serializer_override = getattr(cls, "get_serializer_class", None) is not ModelViewSet.get_serializer_class
        queryset = getattr(cls, "queryset", None)
        has_queryset_override = getattr(cls, "get_queryset", None) is not ModelViewSet.get_queryset

        if serializer_class is None and not has_serializer_override:
            failures.append(f"{cls.__name__}: missing serializer_class/get_serializer_class")
        if queryset is None and not has_queryset_override:
            failures.append(f"{cls.__name__}: missing queryset/get_queryset")

    assert failures == [], "\n".join(sorted(failures))


def test_registered_permission_codes_used_by_admin_surfaces_are_known():
    import re
    from users.admin_apis import KNOWN_PERMISSIONS

    known = set(KNOWN_PERMISSIONS)
    failures = []
    for path in SOURCE_ROOT.rglob("*.py"):
        if not any(
            marker in str(path)
            for marker in (
                "/admin_apis.py",
                "/admin_services.py",
                "/admin_login_settings.py",
                "/admin_tables_api.py",
                "/admin_permissions.py",
            )
        ):
            continue

        source = path.read_text(encoding="utf-8")
        for code in sorted(set(re.findall(r"['\"]([a-z_]+\.(?:view|manage|create|delete|write|read|apply|start|stop|restart|purge))['\"]", source))):
            if code not in known:
                failures.append(f"{path}: unknown permission code {code}")

    assert failures == [], "\n".join(failures)
