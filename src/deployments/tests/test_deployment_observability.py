import sys
import types
from contextlib import contextmanager
from types import SimpleNamespace

import pytest

from deployments.observability import deployment_span


def test_deployment_span_preserves_exceptions_from_deployment_body(monkeypatch):
    span = SimpleNamespace(set_attribute=lambda *_args: None)

    @contextmanager
    def fake_span_context(_name):
        yield span

    fake_trace = SimpleNamespace(
        get_tracer=lambda _name: SimpleNamespace(
            start_as_current_span=fake_span_context
        )
    )
    fake_opentelemetry = types.ModuleType("opentelemetry")
    fake_opentelemetry.trace = fake_trace
    monkeypatch.setitem(sys.modules, "opentelemetry", fake_opentelemetry)

    with pytest.raises(ValueError, match="original deployment failure"):
        with deployment_span("deployment.test", attributes={"deployment.id": "123"}):
            raise ValueError("original deployment failure")
