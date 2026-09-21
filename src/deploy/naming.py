"""Canonical deployment-name normalization and service-scoped allocation."""

from __future__ import annotations

from django.db.models import QuerySet


MAX_DEPLOY_NAME_LENGTH = 50


def normalize_deploy_name(value: object, *, fallback: str = "deploy") -> str:
    """Normalize a requested deployment name without crossing the DB limit."""
    name = str(value or fallback).strip()[:MAX_DEPLOY_NAME_LENGTH]
    return name or fallback[:MAX_DEPLOY_NAME_LENGTH]


def allocate_deploy_name(service, requested_name: object = None, *, deploy_queryset: QuerySet | None = None) -> str:
    """Return a name unused by deployments belonging to ``service``.

    The caller must perform allocation and creation in one transaction. The
    database service/name constraint remains the final race-safety boundary.
    """
    base = normalize_deploy_name(requested_name, fallback=getattr(service, "name", "deploy"))
    queryset = deploy_queryset
    if queryset is None:
        from .models import Deploy

        queryset = Deploy.objects

    candidate = base
    index = 2
    while queryset.filter(service=service, name=candidate).exists():
        suffix = f"-{index}"
        candidate = f"{base[:MAX_DEPLOY_NAME_LENGTH - len(suffix)]}{suffix}"
        index += 1
    return candidate
