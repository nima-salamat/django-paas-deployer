"""Contract tests for the repository-local Agent documentation lookup."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
CLI = ROOT / "scripts" / "agent_docs.py"


def _search(*args: str) -> dict:
    result = subprocess.run(
        [sys.executable, str(CLI), "search", *args, "--json"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=20,
        check=False,
    )
    assert result.returncode == 0, result.stderr or result.stdout
    return json.loads(result.stdout)


def test_model_lookup_returns_documentation_and_live_source_symbol():
    payload = _search("ServiceRevision", "--kind", "model")
    results = payload["results"]

    assert payload["count"] > 0
    assert any(
        item["source"]
        and item["title"] == "ServiceRevision"
        and item["path"] == "src/services/models.py"
        and item["line"] > 0
        and "service" in item["summary"].casefold()
        for item in results
    )
    assert any(
        item["path"] == "documentation/apps/services/models.md"
        for item in results
    )


def test_api_lookup_resolves_agent_rebuild_route_to_url_source():
    payload = _search(
        "/agent/v1/services/{service_id}/rebuild",
        "--kind",
        "api",
    )

    assert payload["count"] > 0
    assert any(
        item["source"]
        and "agent/v1/services/" in item["title"]
        and "rebuild" in item["title"]
        and item["path"] == "src/agent/urls.py"
        and item["line"] > 0
        for item in payload["results"]
    )
    assert any(
        item["path"] == "documentation/apps/agent/api.md"
        for item in payload["results"]
    )


def test_system_lookup_finds_deployment_reconciliation_documentation():
    payload = _search("runtime reconciliation", "--kind", "system")

    assert payload["count"] > 0
    assert any(
        "reconciliation" in item["title"].casefold()
        or "reconciliation" in item["summary"].casefold()
        for item in payload["results"]
    )


def test_agent_api_matrix_covers_every_central_contract_with_a_purpose():
    import re

    contracts = (ROOT / "src" / "agent" / "contracts.py").read_text(encoding="utf-8")
    api_docs = (ROOT / "documentation" / "apps" / "agent" / "api.md").read_text(encoding="utf-8")
    entries = re.findall(
        r'_contract\("([^"]+)",\s*"([^"]+)"',
        contracts,
    )
    matrix = api_docs.split("## Complete endpoint matrix", 1)[1].split(
        "## Request body schemas", 1
    )[0]

    assert entries
    assert "| Method | Endpoint | Purpose |" in matrix
    for endpoint, method in entries:
        assert f"| `{method}` | `{endpoint}` |" in matrix


def test_documentation_audit_has_no_model_or_api_guide_gaps():
    result = subprocess.run(
        [sys.executable, str(CLI), "audit", "--json"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=30,
        check=False,
    )
    assert result.returncode == 0, result.stderr or result.stdout
    report = json.loads(result.stdout)
    assert report["models_missing_from_docs"] == []
    assert report["apps_without_api_guide"] == []
    assert "django" not in report["apps_with_routes"]
    assert report["models_discovered"] == 92
    assert report["persisted_models_discovered"] == 91
    assert report["abstract_models_discovered"] == 1
    assert report["abstract_models"][0]["model"] == "PermissionMixin"


def test_root_mounted_service_status_alias_is_attributed_to_services_app():
    payload = _search("/api/services/service_status/", "--kind", "api")

    assert payload["count"] > 0
    assert any(
        item["source"]
        and item["app"] == "services"
        and item["path"] == "src/config/urls.py"
        and "/api/services/service_status/" in item["title"]
        for item in payload["results"]
    )
