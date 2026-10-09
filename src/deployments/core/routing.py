"""Shared public-host resolution for deployment runtimes.

The control plane exposes services at:
    <docker_service_name>.<DEPLOYMENT_DOMAIN>

An endpoint hostname remains an explicit override when supplied.
"""
from __future__ import annotations

import os
from types import SimpleNamespace
from typing import Any

from django.conf import settings


def deployment_domain() -> str:
    value = getattr(settings, "DEPLOYMENT_DOMAIN", None)
    if not value:
        value = os.environ.get("DEPLOYMENT_DOMAIN", "")
    return str(value or "").strip().strip(".").lower()


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


def public_http_endpoints(config: Any) -> list[Any]:
    """Return public HTTP-family endpoints, including the legacy port route."""
    endpoints = [
        item for item in (getattr(config, "endpoints", None) or ())
        if getattr(item, "enabled", False)
        and getattr(item, "exposure", "") == "public"
        and getattr(item, "protocol", "") in {"http", "https", "ws"}
    ]
    if endpoints:
        return endpoints

    # Older deployments may only have the platform/container port and no
    # ServiceEndpoint row yet. APP services have historically been routed by
    # that port, so keep that compatibility path in both Docker and Swarm.
    try:
        port = int(getattr(config, "port", 0) or 0)
    except (TypeError, ValueError):
        port = 0
    platform_type = str(getattr(config, "platform_type", "") or "").lower()
    labels = getattr(config, "labels", {}) or {}
    process_name = str(labels.get("process.name") or "web").strip().lower()
    if port > 0 and process_name == "web" and platform_type in {"app", "application"}:
        return [SimpleNamespace(
            name="http",
            target_port=port,
            published_port=None,
            protocol="http",
            exposure="public",
            hostname="",
            path="",
            tls=False,
            enabled=True,
            metadata={},
        )]
    return []
