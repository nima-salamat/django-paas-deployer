"""Sanitized public HTTP error pages for web requests and JSON errors for APIs."""
from __future__ import annotations

from django.http import JsonResponse
from django.shortcuts import render


def _error_context(code: int):
    titles = {400: "Bad request", 403: "Access denied", 404: "Page not found", 500: "Something went wrong"}
    messages = {
        400: "The request could not be processed.",
        403: "You do not have permission to access this resource.",
        404: "The requested resource could not be found.",
        500: "The service could not complete the request.",
    }
    return {"status_code": code, "title": titles[code], "message": messages[code]}


def _respond(request, code: int):
    context = _error_context(code)
    accept = (request.headers.get("Accept") or "").lower()
    is_json = "application/json" in accept or request.path.startswith("/api/")
    if is_json:
        return JsonResponse(
            {"detail": context["message"], "status_code": code},
            status=code,
        )
    return render(request, "errors/error.html", context, status=code)


def error_400(request, exception=None):
    return _respond(request, 400)


def error_403(request, exception=None):
    return _respond(request, 403)


def error_404(request, exception=None):
    return _respond(request, 404)


def error_500(request):
    return _respond(request, 500)
