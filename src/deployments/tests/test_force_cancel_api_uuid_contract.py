"""Regression contract for the force-cancel deployment event identifier."""

import ast
from pathlib import Path


def test_force_cancel_api_imports_uuid_for_terminal_event():
    source_path = Path(__file__).resolve().parents[2] / "services" / "api" / "runtime.py"
    source = source_path.read_text(encoding="utf-8")
    module = ast.parse(source)

    assert any(
        isinstance(node, ast.Import)
        and any(alias.name == "uuid" for alias in node.names)
        for node in module.body
    ), "runtime.py must import uuid before force-cancel creates its event_id"

    endpoint = next(
        node for node in ast.walk(module)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        and node.name == "force_cancel_deploy_apiview"
    )
    assert any(
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and isinstance(node.func.value, ast.Name)
        and node.func.value.id == "uuid"
        and node.func.attr == "uuid4"
        for node in ast.walk(endpoint)
    ), "force-cancel must generate a unique outbox event_id"
