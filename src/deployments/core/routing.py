"""Shared public-host resolution for deployment runtimes.

The control plane exposes services at:
    <docker_service_name>.<DEPLOYMENT_DOMAIN>

An endpoint hostname remains an explicit override when supplied.
"""
from __future__ import annotations

import os
from typing import Any

from django.conf import settings


def deployment_domain() -> str:
    value = getattr(settings, "DEPLOYMENT_DOMAIN", None)
    if not value:
        value = os.environ.get("DEPLOYMENT_DOMAIN", "")
    return str(value or "").strip().strip(".")


def resolve_public_host(config: Any, endpoint: Any) -> str:
    """Return the effective hostname that public HTTP routing must use."""
    explicit = str(
        getattr(endpoint, "hostname", None)
        or getattr(config, "public_host", None)
        or ""
    ).strip().lower().rstrip(".")
    if explicit:
        return explicit

    service_name = str(getattr(config, "name", None) or "").strip().lower().strip(".")
    domain = deployment_domain()
    if service_name and domain:
        return f"{service_name}.{domain}"
    return service_name
