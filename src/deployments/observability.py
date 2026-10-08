"""Deployment tracing and diagnostic-error integration."""

from __future__ import annotations

import os
import re
from contextlib import contextmanager
from typing import Any, Iterator

_SECRET = re.compile(r"(password|secret|token|api[_-]?key|private[_-]?key|authorization|credential)", re.I)

def _scrub(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(k): "[REDACTED]" if _SECRET.search(str(k)) else _scrub(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_scrub(v) for v in value]
    if isinstance(value, str) and len(value) > 4096:
        return value[:4096] + "…[TRUNCATED]"
    return value

def configure() -> None:
    try:
        import sentry_sdk
        dsn = os.environ.get("SENTRY_DSN", "").strip()
        if dsn:
            sentry_sdk.init(
                dsn=dsn,
                send_default_pii=False,
                traces_sample_rate=float(os.environ.get("SENTRY_TRACES_SAMPLE_RATE", "0")),
                environment=os.environ.get("SENTRY_ENVIRONMENT") or os.environ.get("DJANGO_ENV") or "production",
            )
    except Exception:
        pass

    try:
        from opentelemetry import trace
        from opentelemetry.sdk.resources import Resource
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.trace.export import BatchSpanProcessor
        provider = trace.get_tracer_provider()
        if provider.__class__.__name__ == "ProxyTracerProvider":
            provider = TracerProvider(resource=Resource.create({"service.name": "django-paas-deployer"}))
            endpoint = os.environ.get("OTEL_EXPORTER_OTLP_ENDPOINT", "").strip()
            if endpoint:
                from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
                provider.add_span_processor(BatchSpanProcessor(OTLPSpanExporter(endpoint=endpoint)))
            trace.set_tracer_provider(provider)
    except Exception:
        pass

@contextmanager
def deployment_span(name: str, *, attributes: dict[str, Any] | None = None) -> Iterator[Any]:
    # Keep optional tracing setup failures non-fatal, but never catch exceptions
    # raised by the deployment body across the yield. Catching those exceptions
    # and yielding a second time violates contextlib's generator protocol and
    # masks the real deployment failure with "generator didn't stop after throw()".
    try:
        from opentelemetry import trace
        tracer = trace.get_tracer("passdeployer.deployment")
        span_context = tracer.start_as_current_span(name)
    except Exception:
        yield None
        return

    with span_context as span:
        try:
            for key, value in _scrub(attributes or {}).items():
                if value is not None:
                    span.set_attribute(str(key), str(value))
        except Exception:
            # Tracing attributes must never make a deployment fail.
            pass
        yield span

def capture_exception(exc: BaseException, *, tags: dict[str, Any] | None = None, context: dict[str, Any] | None = None) -> None:
    try:
        import sentry_sdk
        with sentry_sdk.push_scope() as scope:
            for key, value in _scrub(tags or {}).items():
                scope.set_tag(str(key), str(value))
            if context:
                scope.set_context("deployment", _scrub(context))
            sentry_sdk.capture_exception(exc)
    except Exception:
        return

__all__ = ["configure", "deployment_span", "capture_exception"]
