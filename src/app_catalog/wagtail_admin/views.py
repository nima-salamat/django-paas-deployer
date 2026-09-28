from __future__ import annotations

from functools import wraps
from urllib.parse import urlsplit

from django.contrib import messages
from django.core.exceptions import PermissionDenied
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.http import require_http_methods

from app_catalog.executor import ApplicationStackExecutor
from app_catalog.models import ApplicationInstance, ApplicationStatus
from app_catalog.tasks import cancel_application_installation


def _operator_required(view):
    @wraps(view)
    def wrapped(request, *args, **kwargs):
        user = getattr(request, "user", None)
        if not user or not user.is_authenticated or not user.is_staff:
            raise PermissionDenied
        if not user.is_superuser and not user.has_perm("app_catalog.change_applicationinstance"):
            raise PermissionDenied
        return view(request, *args, **kwargs)
    return wrapped


def _safe_next(request) -> str:
    value = str(request.POST.get("next") or request.GET.get("next") or "").strip()
    parsed = urlsplit(value)
    if value and not parsed.scheme and not parsed.netloc and value.startswith("/") and not value.startswith("//"):
        return value
    return reverse("wagtailadmin_home")


@_operator_required
@require_http_methods(["GET", "POST"])
def application_instance_cancel(request, pk):
    instance = get_object_or_404(ApplicationInstance, pk=pk)
    next_url = _safe_next(request)
    if instance.status in {ApplicationStatus.RUNNING, ApplicationStatus.FAILED, ApplicationStatus.CANCELLED}:
        messages.info(request, f"Application {instance.name} is already terminal and cannot be cancelled.")
        return redirect(next_url)
    if request.method == "POST":
        try:
            cancel_application_installation.delay(str(instance.pk), "Application installation cancelled by operator.")
        except Exception:
            try:
                ApplicationStackExecutor(str(instance.pk)).cancel(reason="Application installation cancelled by operator.")
            except Exception as exc:
                messages.error(request, f"Cancellation failed for {instance.name}: {exc}")
            else:
                messages.warning(request, f"Cancellation applied synchronously for {instance.name}; the coordinator will reconcile remaining child work.")
        else:
            messages.success(request, f"Cancellation requested for {instance.name}.")
        return redirect(next_url)
    return render(request, "app_catalog/wagtail/application_instance_cancel.html", {"instance": instance, "next_url": next_url})
