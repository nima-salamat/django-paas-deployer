"""Production-safe DRF renderers and exception handling."""
from __future__ import annotations

from typing import Any

from rest_framework.renderers import JSONRenderer
from rest_framework.views import exception_handler as drf_exception_handler


class ProductionJSONRenderer(JSONRenderer):
    """JSON-only API renderer with a stable, compact production format.

    DRF's BrowsableAPIRenderer is deliberately excluded from production so the
    API cannot expose an interactive framework UI, route metadata, or HTML
    debug-style response pages to clients.
    """

    charset = "utf-8"

    def render(self, data: Any, accepted_media_type=None, renderer_context=None):
        return super().render(data, accepted_media_type, renderer_context)


def production_exception_handler(exc, context):
    """Return API-safe error payloads without Python/framework internals."""
    response = drf_exception_handler(exc, context)
    if response is None:
        from rest_framework.response import Response
        return Response(
            {"detail": "An internal server error occurred."},
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
            data = {"detail": "Request could not be completed."}
    elif isinstance(data, list):
        data = {"detail": data}
    else:
        data = {"detail": str(data) if response.status_code < 500 else "Request failed."}

    response.data = data
    return response
