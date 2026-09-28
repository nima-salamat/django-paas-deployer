from __future__ import annotations

from functools import wraps
from urllib.parse import urlsplit

from django.contrib import messages
from django.core.exceptions import PermissionDenied
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.http import require_http_methods

from deploy.base_images import request_base_runtime_image_build
from deploy.models import BaseRuntimeImage, Deploy
from deployments.application.cancel import CancelDeploymentUseCase
from deployments.infrastructure.django_cancellation import DjangoDeploymentCancellationGateway


def _operator_required(view):
    @wraps(view)
    def wrapped(request, *args, **kwargs):
        user = getattr(request, "user", None)
        if not user or not user.is_authenticated or not user.is_staff:
            raise PermissionDenied
        if not user.is_superuser and not user.has_perm("deploy.change_baseruntimeimage"):
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
def base_runtime_image_control(request, pk, operation):
    row = get_object_or_404(BaseRuntimeImage, pk=pk)
    if operation not in {"build", "renew"}:
        raise PermissionDenied
    next_url = _safe_next(request)
    title = "Build / Ensure Available" if operation == "build" else "Renew / Rebuild"
    force_rebuild = operation == "renew"
    if request.method == "POST":
        try:
            result = request_base_runtime_image_build(row.pk, force_rebuild=force_rebuild)
        except Exception as exc:
            messages.error(request, f"{title} failed for {row.image_ref}: {exc}")
        else:
            if result.get("cache_hit"):
                messages.info(request, f"{row.image_ref} is already ready and compatible; no build was queued.")
            elif result.get("coalesced"):
                if result.get("rebuild_requested"):
                    messages.warning(request, f"{row.image_ref} is already building; the requested renewal will run after the active build completes.")
                else:
                    messages.info(request, f"{row.image_ref} is already being built. No duplicate build was queued.")
            else:
                messages.success(request, f"{title} queued for {row.image_ref}.")
        return redirect(next_url)
    return render(request, "deploy/wagtail/base_runtime_image_control.html", {
        "row": row, "operation": operation, "title": title,
        "force_rebuild": force_rebuild, "next_url": next_url,
    })


def _deploy_operator_required(view):
    @wraps(view)
    def wrapped(request, *args, **kwargs):
        user = getattr(request, "user", None)
        if not user or not user.is_authenticated or not user.is_staff:
            raise PermissionDenied
        if not user.is_superuser and not user.has_perm("deploy.change_deploy"):
            raise PermissionDenied
        return view(request, *args, **kwargs)
    return wrapped


@_deploy_operator_required
@require_http_methods(["GET", "POST"])
def deployment_cancel(request, pk):
    deploy = get_object_or_404(Deploy, pk=pk)
    next_url = _safe_next(request)
    if str(deploy.status).lower() not in {"pending", "running", "rolling_back"}:
        messages.info(request, f"Deployment {deploy.name} is not cancellable in state {deploy.status}.")
        return redirect(next_url)
    if request.method == "POST":
        try:
            result = CancelDeploymentUseCase(DjangoDeploymentCancellationGateway()).execute(deploy.pk)
        except Exception as exc:
            messages.error(request, f"Cancellation failed for {deploy.name}: {exc}")
        else:
            if result.decision.target_status:
                messages.success(request, f"Deployment {deploy.name} cancelled.")
            else:
                messages.success(request, f"Cancellation requested for {deploy.name}; the owning worker will finish cleanup.")
        return redirect(next_url)
    return render(request, "deploy/wagtail/deployment_cancel.html", {"deploy": deploy, "next_url": next_url})
