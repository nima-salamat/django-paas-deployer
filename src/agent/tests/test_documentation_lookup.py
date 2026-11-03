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
