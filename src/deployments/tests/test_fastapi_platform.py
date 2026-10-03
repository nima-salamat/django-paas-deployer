from __future__ import annotations

from pathlib import Path

from deployments.core.platforms.python.fastapi_plat import FastAPIPlatform


def _project(tmp_path: Path, files: dict[str, str]) -> dict[str, str]:
    index: dict[str, str] = {}
    for rel, text in files.items():
        path = tmp_path / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
        index[rel] = str(path)
    return index


def test_detects_fastapi_from_dependency_and_prefers_fastapi_entrypoint(tmp_path):
    index = _project(
        tmp_path,
        {
            "requirements.txt": "fastapi>=0.115\nuvicorn[standard]\n",
            "main.py": "from fastapi import FastAPI\napp = FastAPI()\n",
        },
    )
    platform = FastAPIPlatform(str(tmp_path))

    result = platform.detect(index)
    inspected = platform.inspect(index)

    assert result is not None
    assert result.platform == "fastapi"
    assert result.framework == "fastapi"
    assert result.confidence >= 0.9
    assert inspected["server_type"] == "asgi"
    assert inspected["entrypoint"] == "main:app"
    assert inspected["start_command"].startswith("uvicorn main:app")
    assert inspected["fastapi_entrypoint_detected"] is True


def test_detects_nested_main_module(tmp_path):
    index = _project(
        tmp_path,
        {
            "requirements.txt": "fastapi==0.115.6\n",
            "backend/main.py": "from fastapi import FastAPI\napplication = FastAPI()\n",
        },
    )
    inspected = FastAPIPlatform(str(tmp_path)).inspect(index)

    assert inspected["entrypoint"] == "backend.main:application"


def test_source_detection_requires_fastapi_evidence(tmp_path):
    index = _project(
        tmp_path,
        {
            "main.py": "from flask import Flask\napp = Flask(__name__)\n",
        },
    )
    assert FastAPIPlatform(str(tmp_path)).detect(index) is None


def test_does_not_invent_entrypoint_when_fastapi_app_is_missing(tmp_path):
    index = _project(
        tmp_path,
        {
            "requirements.txt": "fastapi>=0.115\n",
            "main.py": "from fastapi import FastAPI\n\n# application is wired elsewhere\n",
        },
    )
    platform = FastAPIPlatform(str(tmp_path))
    inspected = platform.inspect(index)

    assert inspected["fastapi_entrypoint_detected"] is False
    assert "entrypoint" not in inspected
    assert "start_command" not in inspected
    assert platform.validate(
        type("Config", (), {"entrypoint": None, "start_command": None})()
    )[-1].startswith("FastAPI entrypoint could not be detected.")


def test_starlette_only_project_is_not_misclassified_as_fastapi(tmp_path):
    index = _project(
        tmp_path,
        {
            "requirements.txt": "starlette>=0.40\n",
            "main.py": "from starlette.applications import Starlette\napp = Starlette()\n",
        },
    )
    assert FastAPIPlatform(str(tmp_path)).detect(index) is None
