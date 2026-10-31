"""Production-safe DRF renderers and exception handling."""
from __future__ import annotations

from typing import Any
import logging

from rest_framework.renderers import JSONRenderer
from rest_framework.views import exception_handler as drf_exception_handler
from django.utils.translation import gettext as _

logger = logging.getLogger(__name__)


def _translate_api_error_value(value):
    """Translate known user-facing errors without modifying unrelated values."""
    if isinstance(value, str):
        return _(value)
    if isinstance(value, list):
        return [_translate_api_error_value(item) for item in value]
    if isinstance(value, tuple):
        return tuple(_translate_api_error_value(item) for item in value)
    if isinstance(value, dict):
        return {
            key: value[key] if key in {"protected", "supported_languages", "code"} else _translate_api_error_value(child)
            for key, child in value.items()
        }
    return value


def _translate_api_metadata(value, context=None):
    """Translate table-schema labels without rewriting user-owned content."""
    if isinstance(value, list):
        return [_translate_api_metadata(item, context=context) for item in value]
    if not isinstance(value, dict):
        return value

    localized = {}
    for key, child in value.items():
        if (
            key == "label"
            and context in {"tables", "fields", "choices"}
            and isinstance(child, str)
        ):
            localized[key] = _(child)
        elif (
            key in {"verbose_name", "help_text"}
            and context == "fields"
            and isinstance(child, str)
        ):
            localized[key] = _(child)
        elif key == "_display" and isinstance(child, dict):
            localized[key] = {
                name: _(label) if isinstance(label, str) else label
                for name, label in child.items()
            }
        else:
            localized[key] = _translate_api_metadata(child, context=key)
    return localized


def _localize_api_payload(data, status_code: int):
    """Localize standard response envelopes across all DRF API namespaces."""
    localized = _translate_api_metadata(data)
    if not isinstance(localized, dict):
        return _translate_api_error_value(localized) if status_code >= 400 else localized

    # Static API messages are translated on success and failure. User-written
    # content fields (text/body/description/log output) are deliberately untouched.
    for key in ("message", "detail", "error", "non_field_errors", "errors"):
        if key in localized:
            localized[key] = _translate_api_error_value(localized[key])
    if status_code >= 400:
        for key, child in tuple(localized.items()):
            if key not in {
                "protected", "supported_languages", "code", "message",
                "detail", "error", "non_field_errors", "errors",
            }:
                localized[key] = _translate_api_error_value(child)
    return localized


class ProductionJSONRenderer(JSONRenderer):
    """JSON-only API renderer with a stable, compact production format.

    DRF's BrowsableAPIRenderer is deliberately excluded from production so the
    API cannot expose an interactive framework UI, route metadata, or HTML
    debug-style response pages to clients.
    """

    charset = "utf-8"
    ensure_ascii = False

    def render(self, data: Any, accepted_media_type=None, renderer_context=None):
        response = (renderer_context or {}).get("response")
        status_code = int(getattr(response, "status_code", 200) or 200)
        return super().render(
            _localize_api_payload(data, status_code),
            accepted_media_type,
            renderer_context,
        )


def production_exception_handler(exc, context):
    """Return API-safe error payloads without Python/framework internals."""
    response = drf_exception_handler(exc, context)
    if response is None:
        # DRF intentionally gives us no response for unhandled exceptions.
        # Keep the public response sanitized, but never lose the traceback:
        # otherwise production only reports a useless generic 500.
        request = context.get("request")
        view = context.get("view")
        logger.exception(
            "Unhandled DRF exception: %s %s view=%s",
            getattr(request, "method", "?"),
            getattr(request, "path", "?"),
            type(view).__name__ if view is not None else "?",
            exc_info=(type(exc), exc, exc.__traceback__),
        )
        from rest_framework.response import Response
        return Response(
            {"detail": _("An internal server error occurred.")},
            status=500,
            content_type="application/json",
        )

    data = response.data
    if isinstance(data, dict):
        # Keep validation field errors intact, but remove DRF's verbose/debug
        # keys when present. Never serialize exception repr/traceback here.
        data = {
            key: value
            for key, value in data.items()
            if key not in {"exception", "traceback", "debug", "__debug__"}
        }
        if not data:
            data = {"detail": _("Request could not be completed.")}
    elif isinstance(data, list):
        data = {"detail": data}
    else:
        data = {"detail": str(data) if response.status_code < 500 else _("Request failed.")}

    response.data = data
    return response
