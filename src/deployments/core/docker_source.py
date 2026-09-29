"""Secure Dockerfile and single-service Compose inspection for tenant Docker mode."""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
import os
import shlex
import re
from typing import Any
import yaml

from deployments.common.exceptions import DeploymentSecurityError
from deployments.common.security import is_safe_archive_name


MAX_DOCKERFILE_BYTES = 512 * 1024
MAX_COMPOSE_BYTES = 2 * 1024 * 1024
MAX_ENV_BYTES = 256 * 1024

SENSITIVE_KEY_RE = re.compile(
    r"(?i)(password|passwd|secret|token|api[_-]?key|private[_-]?key|authorization|credential|access[_-]?key)"
)

CRITICAL_COMPOSE_KEYS = {
    "deploy", "privileged", "network_mode", "pid", "ipc", "devices",
    "cap_add", "cap_drop", "security_opt", "sysctls", "ulimits", "runtime",
    "secrets", "configs", "credential_spec", "container_name", "hostname",
    "domainname", "extra_hosts", "dns", "dns_search", "init", "profiles", "extends",
    "links", "external_links", "volumes_from", "user", "platform",
}

RESERVED_LABEL_PREFIXES = (
    "traefik.", "com.docker.", "io.passdeployer.", "managed-by", "deployment.id", "service.id",
)

DANGEROUS_COMMAND_RE = re.compile(
    r"(?i)(?:^|[\s;&|])("
    r"nsenter|unshare|modprobe|insmod|setcap|mount|docker\s+run|docker\s+exec|"
    r"dockerd\b|containerd\b|/var/run/docker\.sock|"
    r"curl\s+[^|\n]+\|\s*(?:sh|bash|python|python3|php)|"
    r"wget\s+[^|\n]+\|\s*(?:sh|bash|python|python3|php)|"
    r"curl\s+[^\n]+(?:-o|--output|-O)\s+[^\n]+(?:&&|;|\|)\s*(?:sh|bash|python|python3|php)|"
    r"wget\s+[^\n]+(?:-O|--output-document)\s+[^\n]+(?:&&|;|\|)\s*(?:sh|bash|python|python3|php)|"
    r"sh\s+-c\s+[\"']?\$\(\s*(?:curl|wget)\b|"
    r"python(?:3)?\s+-c\s+[^\n]*(?:urllib|requests|urlopen)|"
    r"php\s+-r\s+[^\n]*(?:curl_init|file_get_contents)\s*\("
    r"|chmod\s+[^ \n]+\s+\+s"
    r")"
)

RUNTIME_DOCKER_RE = re.compile(
    r"(?i)(^|[\s;&|])(dockerd\b|docker\s+run\b|docker\s+exec\b|nsenter\b|unshare\b|/var/run/docker\.sock|mount\b)"
)

SENSITIVE_CONTEXT_RE = re.compile(
    r"(?i)(^|[/\\])(?:\.env(?:\.[^/\\]+)?|.*\.(?:pem|key)|id_rsa(?:\.[^/\\]+)?|"
    r"credentials?(?:\.[^/\\]+)?|secrets?(?:[/\\]|\.|$)|\.aws(?:[/\\]|$)|\.ssh(?:[/\\]|$))"
)

DIND_IMAGE_RE = re.compile(r"(?i)^FROM\s+(?:[^\s/]+/)?docker(?::[^\s]+)?[-:]dind(?:@sha256:[^\s]+)?")


@dataclass(frozen=True)
class DockerPolicyFinding:
    code: str
    severity: str
    action: str
    message: str
    path: str = ""
    line: int | None = None

    def as_dict(self) -> dict[str, Any]:
        result = {"code": self.code, "severity": self.severity, "action": self.action, "message": self.message}
        if self.path:
            result["path"] = self.path
        if self.line is not None:
            result["line"] = self.line
        return result


@dataclass
class DockerSourceResolution:
    source_kind: str
    source_file: str
    dockerfile_text: str
    runtime: dict[str, Any] = field(default_factory=dict)
    volumes: list[dict[str, Any]] = field(default_factory=list)
    findings: list[DockerPolicyFinding] = field(default_factory=list)

    @property
    def blocked(self) -> bool:
        return any(f.action == "deny" for f in self.findings)

    def report(self) -> dict[str, Any]:
        return {
            "source_kind": self.source_kind,
            "source_file": self.source_file,
            "blocked": self.blocked,
            "findings": [f.as_dict() for f in self.findings],
            "runtime": {
                "environment_keys": sorted((self.runtime.get("environment") or {}).keys()),
                "has_command": bool(self.runtime.get("command")),
                "has_entrypoint": bool(self.runtime.get("entrypoint")),
                "target_port": self.runtime.get("port"),
                "public": bool(self.runtime.get("public")),
                "read_only": bool(self.runtime.get("read_only")),
            },
            "volume_count": len(self.volumes),
        }


def _safe_relative(value: Any, *, field: str) -> str:
    text = str(value or "").replace("\\", "/").strip()
    if not text or text.startswith("/") or re.match(r"^[A-Za-z]:/", text) or not is_safe_archive_name(text):
        raise DeploymentSecurityError(
            f"{field} must be a relative path inside the uploaded application.",
            stage="docker_source_validation",
            details={"field": field, "value": text},
        )
    normalized = os.path.normpath(text).replace("\\", "/")
    if normalized in {".", ".."} or normalized.startswith("../"):
        raise DeploymentSecurityError(
            f"{field} escapes the uploaded application.",
            stage="docker_source_validation",
            details={"field": field, "value": text},
        )
    return normalized


def _safe_target(value: Any) -> str:
    text = str(value or "").replace("\\", "/").strip()
    if not text.startswith("/") or text.startswith("//") or "/../" in f"/{text}/":
        raise DeploymentSecurityError(
            f"Invalid container mount target '{text}'.",
            stage="docker_source_validation",
        )
    return os.path.normpath(text).replace("\\", "/")


def _read_file(root: Path, rel: str, limit: int) -> str:
    rel = _safe_relative(rel, field="source file")
    target = (root / rel).resolve()
    if root not in target.parents and target != root:
        raise DeploymentSecurityError(
            "Source file escapes the application root.",
            stage="docker_source_validation",
        )
    if not target.is_file():
        raise DeploymentSecurityError(
            f"Source file '{rel}' does not exist.",
            stage="docker_source_validation",
        )
    if target.stat().st_size > limit:
        raise DeploymentSecurityError(
            f"Source file '{rel}' exceeds the supported size limit.",
            stage="docker_source_validation",
        )
    return target.read_text("utf-8", errors="replace")


def _parse_env_file(root: Path, rel: str) -> dict[str, str]:
    text = _read_file(root, rel, MAX_ENV_BYTES)
    result: dict[str, str] = {}
    for number, raw in enumerate(text.splitlines(), 1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[7:].lstrip()
        if "=" not in line:
            raise DeploymentSecurityError(
                f"Invalid env_file entry at {rel}:{number}.",
                stage="docker_source_validation",
            )
        key, value = line.split("=", 1)
        key = key.strip()
        if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]{0,127}", key):
            raise DeploymentSecurityError(
                f"Invalid environment variable name '{key}'.",
                stage="docker_source_validation",
            )
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in {'"', "'"}:
            value = value[1:-1]
        raw_value = value
        if (SENSITIVE_KEY_RE.search(key) or key.upper() in {"DOCKER_HOST", "DOCKER_CONTEXT", "DOCKER_CERT_PATH"}) and value and "$" not in raw_value:
            raise DeploymentSecurityError(
                f"Sensitive value for '{key}' must be supplied through PassDeployer secrets, not '{rel}'.",
                stage="docker_source_validation",
                details={"path": rel, "line": number, "key": key},
            )
        result[key] = value
    return result


def _compose_interpolate(value: str, variables: dict[str, str]) -> str:
    if not isinstance(value, str):
        return str(value)
    brace_re = re.compile(r"\$" + r"\{([A-Za-z_][A-Za-z0-9_]*)(?:(:-|-)([^}]*))?\}")
    bare_re = re.compile(r"\$([A-Za-z_][A-Za-z0-9_]*)")

    def brace(match: re.Match[str]) -> str:
        name, op, default = match.group(1), match.group(2), match.group(3)
        if name in variables:
            return str(variables[name])
        if op in {":-", "-"}:
            return default or ""
        raise DeploymentSecurityError(
            f"Compose variable '{name}' is not configured.",
            stage="docker_source_validation",
            details={"variable": name},
        )

    value = brace_re.sub(brace, value)
    return bare_re.sub(lambda m: str(variables[m.group(1)]) if m.group(1) in variables else m.group(0), value)


def _environment(raw: Any, variables: dict[str, str]) -> dict[str, str]:
    result: dict[str, str] = {}
    entries = list(raw.items()) if isinstance(raw, dict) else list(raw or []) if isinstance(raw, list) else []
    for item in entries:
        if isinstance(item, tuple):
            key, value = str(item[0]).strip(), item[1]
            if value is None:
                raise DeploymentSecurityError(
                    f"Compose environment variable '{key}' inherits the control-plane environment.",
                    stage="docker_source_validation",
                )
        else:
            text = str(item)
            if "=" not in text:
                raise DeploymentSecurityError(
                    f"Compose environment entry '{text}' inherits the control-plane environment.",
                    stage="docker_source_validation",
                )
            key, value = text.split("=", 1)
            key = key.strip()
        if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]{0,127}", key):
            raise DeploymentSecurityError(
                f"Invalid environment variable name '{key}'.",
                stage="docker_source_validation",
            )
        raw_value = str(value)
        value = _compose_interpolate(raw_value, variables)
        if SENSITIVE_KEY_RE.search(key) and value and "$" not in raw_value:
            raise DeploymentSecurityError(
                f"Sensitive environment '{key}' must be supplied through PassDeployer secrets.",
                stage="docker_source_validation",
                details={"key": key},
            )
        result[key] = value
    return result


def _command(value: Any, field: str) -> str | None:
    if value in (None, "", []):
        return None
    if isinstance(value, list):
        return " ".join(str(x) for x in value)
    if isinstance(value, str):
        return value.strip() or None
    raise DeploymentSecurityError(
        f"Compose {field} must be a string or list.",
        stage="docker_source_validation",
    )


def analyze_dockerfile(text: str, *, source_file: str) -> list[DockerPolicyFinding]:
    findings: list[DockerPolicyFinding] = []
    logical: list[tuple[int, str]] = []
    pending = ""
    start = 1
    for number, raw in enumerate(text.splitlines(), 1):
        if not pending:
            start = number
        line = raw.rstrip()
        pending += line[:-1] + " " if line.endswith("\\") else line
        if not line.endswith("\\"):
            logical.append((start, pending.strip()))
            pending = ""
    if pending:
        logical.append((start, pending.strip()))

    if not any(line.upper().startswith("FROM ") for _, line in logical):
        findings.append(DockerPolicyFinding("dockerfile_missing_from", "critical", "deny", "Dockerfile must contain FROM.", source_file))

    for number, line in logical:
        upper = line.upper()
        if not line or line.startswith("#"):
            continue
        if upper.startswith("FROM "):
            image_ref = line.split(None, 1)[1].strip().split()[0]
            if DIND_IMAGE_RE.search(line):
                findings.append(DockerPolicyFinding(
                    "dockerfile_dind_base", "critical", "deny",
                    "Docker-in-Docker base images are not allowed for tenant applications.",
                    source_file, number,
                ))
        if upper.startswith(("COPY ", "ADD ")):
            tokens = line.split()
            sources = tokens[1:-1] if len(tokens) >= 3 else []
            for source in sources:
                source_clean = source.strip("'\\\"")
                if SENSITIVE_CONTEXT_RE.search(source_clean):
                    findings.append(DockerPolicyFinding(
                        "dockerfile_sensitive_context_copy", "critical", "deny",
                        f"Sensitive host/project file '{source_clean}' cannot be copied into the application image.",
                        source_file, number,
                    ))
        if upper.startswith("ADD "):
            first = line.split(None, 1)[1].split()[0] if len(line.split(None, 1)) > 1 else ""
            if re.match(r"^https?://", first, re.I):
                findings.append(DockerPolicyFinding(
                    "dockerfile_remote_add", "high", "deny",
                    "Remote ADD URLs are disabled.", source_file, number,
                ))
        if upper.startswith("RUN "):
            if re.search(r"--network(?:=|\s+)host(?:\s|$)", line, re.I):
                findings.append(DockerPolicyFinding(
                    "dockerfile_host_network", "critical", "deny",
                    "RUN --network=host is not allowed.", source_file, number,
                ))
            if re.search(r"--security(?:=|\s+)insecure(?:\s|$)", line, re.I):
                findings.append(DockerPolicyFinding(
                    "dockerfile_insecure_security", "critical", "deny",
                    "RUN --security=insecure is not allowed.", source_file, number,
                ))
            if re.search(r"--device(?:=|\s+)", line, re.I):
                findings.append(DockerPolicyFinding(
                    "dockerfile_device_entitlement", "critical", "deny",
                    "RUN --device is not allowed for tenant Docker builds.",
                    source_file, number,
                ))
            if re.search(r"--mount(?:=|\s+)(?:[^ \n]*,)*type=(bind|secret|ssh)(?:,|\s|$)", line, re.I):
                findings.append(DockerPolicyFinding(
                    "dockerfile_unsafe_mount", "critical", "deny",
                    "Tenant Dockerfile cannot use bind, secret or SSH build mounts.", source_file, number,
                ))
            match = DANGEROUS_COMMAND_RE.search(line)
            if match:
                findings.append(DockerPolicyFinding(
                    "dockerfile_dangerous_command", "high", "deny",
                    f"Dangerous build operation '{match.group(2)}' is not allowed.", source_file, number,
                ))
        if upper.startswith(("ENV ", "ARG ")):
            assignment = line.split(None, 1)[1]
            key = assignment.split("=", 1)[0].strip()
            if SENSITIVE_KEY_RE.search(key) and "=" in assignment and assignment.split("=", 1)[1].strip():
                findings.append(DockerPolicyFinding(
                    "dockerfile_secret_default", "critical", "deny",
                    f"Sensitive Dockerfile variable '{key}' cannot contain a baked-in value.", source_file, number,
                ))
        if upper.startswith("VOLUME "):
            findings.append(DockerPolicyFinding(
                "dockerfile_anonymous_volume", "critical", "deny",
                "Dockerfile VOLUME instructions are disabled because PassDeployer must own and account for persistent storage.",
                source_file, number,
            ))
        if upper.startswith(("CMD ", "ENTRYPOINT ", "HEALTHCHECK ")):
            match = RUNTIME_DOCKER_RE.search(line)
            if match:
                findings.append(DockerPolicyFinding(
                    "dockerfile_dangerous_runtime", "critical", "deny",
                    f"Runtime operation '{match.group(2)}' is not allowed.", source_file, number,
                ))
        if upper.startswith("USER ") and line.split(None, 1)[1].strip().lower() in {"0", "root"}:
            findings.append(DockerPolicyFinding(
                "dockerfile_root_runtime", "warning", "warn",
                "The final image explicitly runs as root.", source_file, number,
            ))
    return findings




MAX_INSPECTED_BUILD_SCRIPTS = 32
MAX_SCRIPT_BYTES = 256 * 1024

_SCRIPT_INTERPRETERS = {"sh", "bash", "dash", "zsh", "ksh", "python", "python3", "node", "nodejs", "php", "perl", "ruby"}
_SCRIPT_NAME_RE = re.compile(r"(?i)\.(?:sh|bash|zsh|ksh|py|js|mjs|cjs|ts|php|pl|pm|rb)$")
_SCRIPT_RISK_RE = re.compile(
    r"(?i)(?:"
    r"\bdocker\s+(?:run|exec|build|compose|service|swarm|system|volume|network|context|info|ps|inspect|cp|pull|push|tag|login)\b|/var/run/docker\.sock|"
    r"\b(?:nsenter|unshare|mount|umount|modprobe|insmod|setcap|chroot)\b|"
    r"\b(?:sudo|su|doas)\b|"
    r"\b(?:curl|wget)\b[^\n|]*\|[ \t]*(?:sh|bash|dash|zsh|python|python3|php)\b|"
    r"\b(?:base64)\b[^\n|]*(?:-d|--decode)[^\n|]*\|[ \t]*(?:sh|bash|dash|zsh|python|python3|php)\b|"
    r"\beval[ \t]+(?:\$\(|\$[A-Za-z_{])|"
    r"\b(?:python|python3)\b[^\n]*(?:socket|subprocess|os\.system|os\.popen)|"
    r"\b(?:node|nodejs)\b[^\n]*(?:child_process|execSync|spawn)\b|"
    r"\bphp\b[^\n]*(?:shell_exec|proc_open|passthru|system)\b"
    r")"
)

def _strip_script_comments(text: str) -> str:
    lines: list[str] = []
    for raw in text.splitlines():
        stripped = raw.lstrip()
        if stripped.startswith(("#", "//")):
            continue
        lines.append(raw)
    return "\n".join(lines)

def _script_argument(tokens: list[str], interpreter: str) -> str | None:
    start = 1
    if interpreter in {"python", "python3", "node", "nodejs", "php", "perl", "ruby"}:
        if start < len(tokens) and tokens[start] in {"-c", "--eval", "-e"}:
            return None
    while start < len(tokens):
        token = tokens[start]
        if token.startswith("-"):
            start += 1
            continue
        return token
    return None

def _candidate_build_scripts(dockerfile_text: str) -> list[tuple[int, str]]:
    candidates: list[tuple[int, str]] = []
    for number, logical in enumerate(dockerfile_text.splitlines(), 1):
        line = logical.strip()
        if not line.upper().startswith("RUN "):
            continue
        command = line[4:].strip()
        for segment in re.split(r"&&|\|\||[;|]", command):
            segment = segment.strip()
            if not segment:
                continue
            try:
                tokens = shlex.split(segment, posix=True)
            except ValueError:
                tokens = segment.split()
            if not tokens:
                continue
            first = tokens[0]
            interpreter = Path(first).name.lower()
            if interpreter in _SCRIPT_INTERPRETERS:
                script = _script_argument(tokens, interpreter)
                if script and (script.startswith(("./", "../")) or _SCRIPT_NAME_RE.search(script)):
                    candidates.append((number, script))
                continue
            if first.startswith(("./", "../")) or _SCRIPT_NAME_RE.search(first):
                candidates.append((number, first))
    return candidates

def analyze_referenced_build_scripts(
    project_root: str,
    dockerfile_text: str,
    *,
    source_file: str,
) -> list[DockerPolicyFinding]:
    root = Path(project_root).resolve()
    findings: list[DockerPolicyFinding] = []
    seen: set[str] = set()

    for line_number, candidate in _candidate_build_scripts(dockerfile_text):
        normalized = candidate.strip("'\"")
        if normalized in seen:
            continue
        seen.add(normalized)
        if len(seen) > MAX_INSPECTED_BUILD_SCRIPTS:
            findings.append(DockerPolicyFinding(
                "dockerfile_too_many_build_scripts",
                "critical",
                "deny",
                f"Build references more than {MAX_INSPECTED_BUILD_SCRIPTS} local scripts; source inspection is bounded.",
                source_file,
                line_number,
            ))
            break

        if normalized.startswith("/"):
            findings.append(DockerPolicyFinding(
                "dockerfile_uninspectable_script",
                "critical",
                "deny",
                f"Build executes an absolute-path script '{normalized}' that cannot be safely mapped to the uploaded source context.",
                source_file,
                line_number,
            ))
            continue

        try:
            rel = _safe_relative(normalized, field="build script")
        except DeploymentSecurityError:
            findings.append(DockerPolicyFinding(
                "dockerfile_unsafe_script_path",
                "critical",
                "deny",
                f"Build script path '{normalized}' is outside the uploaded application context.",
                source_file,
                line_number,
            ))
            continue

        target = (root / rel).resolve()
        if root not in target.parents or not target.is_file():
            findings.append(DockerPolicyFinding(
                "dockerfile_unresolved_script",
                "critical",
                "deny",
                f"Build script '{normalized}' could not be resolved inside the uploaded application context.",
                source_file,
                line_number,
            ))
            continue

        try:
            if target.stat().st_size > MAX_SCRIPT_BYTES:
                findings.append(DockerPolicyFinding(
                    "dockerfile_script_too_large",
                    "critical",
                    "deny",
                    f"Build script '{normalized}' exceeds the source inspection limit.",
                    source_file,
                    line_number,
                ))
                continue
            script_text = target.read_text("utf-8", errors="replace")
        except OSError as exc:
            findings.append(DockerPolicyFinding(
                "dockerfile_script_unreadable",
                "critical",
                "deny",
                f"Build script '{normalized}' could not be inspected: {exc}",
                source_file,
                line_number,
            ))
            continue

        script_text = _strip_script_comments(script_text)
        match = _SCRIPT_RISK_RE.search(script_text) or DANGEROUS_COMMAND_RE.search(script_text)
        if match:
            findings.append(DockerPolicyFinding(
                "dockerfile_dangerous_build_script",
                "critical",
                "deny",
                f"Build script '{normalized}' contains an operation that is not allowed in tenant Docker builds.",
                str(target.relative_to(root)).replace("\\", "/"),
                line_number,
            ))
    return findings


def _volume_bind(source: str) -> bool:
    source = str(source or "").strip()
    return source.startswith(("/", "./", "../", "~/")) or bool(re.match(r"^[A-Za-z]:[\\\\/]", source))


def _compose_volume(raw: Any, service_name: str, findings: list[DockerPolicyFinding]) -> dict[str, str] | None:
    if isinstance(raw, str):
        parts = raw.split(":")
        if len(parts) < 2:
            raise DeploymentSecurityError(
                f"Compose volume '{raw}' on '{service_name}' must specify a target.",
                stage="docker_source_validation",
            )
        source = parts[0]
        target = parts[-2] if len(parts) >= 3 else parts[1]
        mode = parts[-1] if len(parts) >= 3 else "rw"
    elif isinstance(raw, dict):
        source = str(raw.get("source") or raw.get("volume") or "")
        target = str(raw.get("target") or "")
        mode = "ro" if raw.get("read_only") else "rw"
        if str(raw.get("type") or "volume").lower() != "volume":
            source = source or "bind"
            findings.append(DockerPolicyFinding(
                "compose_host_bind_removed", "critical", "strip",
                f"Removed non-managed mount for target '{target}'.", "docker-compose.yml",
            ))
            return None
    else:
        raise DeploymentSecurityError(
            f"Unsupported Compose volume definition on '{service_name}'.",
            stage="docker_source_validation",
        )
    if _volume_bind(source):
        findings.append(DockerPolicyFinding(
            "compose_host_bind_removed", "critical", "strip",
            f"Removed host bind mount for target '{target}'.", "docker-compose.yml",
        ))
        return None
    target = _safe_target(target)
    return {"compose_name": source or service_name, "target": target, "mode": "ro" if mode in {"ro", "readonly"} else "rw"}


def inspect_docker_source(project_root: str, *, environment: dict[str, str] | None = None) -> DockerSourceResolution:
    root = Path(project_root).resolve()
    if not root.is_dir():
        raise DeploymentSecurityError("Docker source project root does not exist.", stage="docker_source_validation")

    compose_name = next((n for n in ("docker-compose.yml", "docker-compose.yaml", "compose.yml", "compose.yaml") if (root / n).is_file()), None)
    dockerfile_name = next((n for n in ("Dockerfile", "dockerfile") if (root / n).is_file()), None)

    if compose_name:
        text = (root / compose_name).read_text("utf-8", errors="replace")
        if len(text.encode()) > MAX_COMPOSE_BYTES:
            raise DeploymentSecurityError("Compose file exceeds the supported size limit.", stage="docker_source_validation")
        try:
            document = yaml.safe_load(text) or {}
        except yaml.YAMLError as exc:
            raise DeploymentSecurityError(f"Invalid Docker Compose YAML: {exc}", stage="docker_source_validation") from exc
        services = document.get("services") if isinstance(document, dict) else None
        if not isinstance(services, dict) or not services:
            raise DeploymentSecurityError("Docker Compose must contain a services mapping.", stage="docker_source_validation")
        if len(services) != 1:
            raise DeploymentSecurityError(
                f"PassDeployer Docker mode supports exactly one application service per Compose file; found {len(services)}.",
                stage="docker_source_validation",
                details={"service_count": len(services), "services": sorted(str(x) for x in services)},
            )
        name, service = next(iter(services.items()))
        name = str(name)
        if not isinstance(service, dict):
            raise DeploymentSecurityError(f"Compose service '{name}' must be a mapping.", stage="docker_source_validation")

        findings: list[DockerPolicyFinding] = []
        for key in sorted(CRITICAL_COMPOSE_KEYS & set(service)):
            findings.append(DockerPolicyFinding(
                f"compose_{key.replace('-', '_')}", "critical", "deny",
                f"Compose service '{name}' uses unsupported '{key}'.", compose_name,
            ))
        if document.get("networks"):
            non_default = [str(k) for k in document["networks"] if str(k) != "default"]
            if non_default:
                findings.append(DockerPolicyFinding(
                    "compose_custom_network", "critical", "deny",
                    "Custom/external Compose networks are not imported; PassDeployer owns networking.", compose_name,
                ))
        service_networks = service.get("networks") or []
        if isinstance(service_networks, dict):
            service_networks = list(service_networks)
        if any(str(item) != "default" for item in service_networks):
            findings.append(DockerPolicyFinding(
                "compose_service_custom_network", "critical", "deny",
                "Service-level custom/external networks are not imported.",
                compose_name,
            ))
        if document.get("secrets") or document.get("configs"):
            findings.append(DockerPolicyFinding(
                "compose_top_level_secrets_or_configs", "critical", "deny",
                "Top-level Compose secrets/configs are not imported.", compose_name,
            ))

        variables: dict[str, str] = {}
        dotenv = root / ".env"
        if dotenv.is_file():
            variables.update(_parse_env_file(root, ".env"))
        variables.update({str(k): str(v) for k, v in (environment or {}).items()})

        env = _environment(service.get("environment"), variables)
        for raw_file in service.get("env_file") or []:
            rel = str(raw_file.get("path") if isinstance(raw_file, dict) else raw_file)
            env = {**_parse_env_file(root, rel), **env}

        build = service.get("build")
        build_args: dict[str, str] = {}
        if isinstance(build, dict):
            raw_args = build.get("args") or {}
            args = list(raw_args.items()) if isinstance(raw_args, dict) else list(raw_args or [])
            for item in args:
                if isinstance(item, tuple):
                    arg_key, arg_value = str(item[0]), item[1]
                else:
                    pair = str(item)
                    if "=" not in pair:
                        raise DeploymentSecurityError(
                            "Compose build.args must provide explicit values or environment references.",
                            stage="docker_source_validation",
                        )
                    arg_key, arg_value = pair.split("=", 1)
                raw_arg = str(arg_value or "")
                if (SENSITIVE_KEY_RE.search(arg_key) or arg_key.upper() in {"DOCKER_HOST", "DOCKER_CONTEXT"}) and raw_arg and "$" not in raw_arg:
                    raise DeploymentSecurityError(
                        f"Sensitive build argument '{arg_key}' must not be baked into a tenant build.",
                        stage="docker_source_validation",
                    )
                build_args[str(arg_key)] = _compose_interpolate(raw_arg, variables)
            build_network = str(build.get("network") or "").strip().lower()
            if build_network == "host":
                findings.append(DockerPolicyFinding(
                    "compose_build_host_network", "critical", "deny",
                    "Compose build.network=host is not allowed.",
                    compose_name,
                ))
            if build.get("secrets"):
                findings.append(DockerPolicyFinding(
                    "compose_build_secrets", "critical", "deny",
                    "Compose build secrets are not supplied to tenant builds.",
                    compose_name,
                ))
        if build:
            context = str(build.get("context") if isinstance(build, dict) else build or ".")
            if context not in {".", "./"}:
                raise DeploymentSecurityError(
                    "Compose build.context must be the application root.",
                    stage="docker_source_validation",
                    details={"context": context},
                )
            dockerfile = str(build.get("dockerfile") if isinstance(build, dict) else "Dockerfile")
            dockerfile_text = _read_file(root, dockerfile, MAX_DOCKERFILE_BYTES)
            source_file = dockerfile
        else:
            image = str(service.get("image") or "").strip()
            if not image or any(ch.isspace() for ch in image) or image.startswith("/"):
                raise DeploymentSecurityError(
                    "Compose application service must declare a valid image or build.",
                    stage="docker_source_validation",
                )
            dockerfile_text = f"FROM {image}\n"
            source_file = "<generated-from-image>"

        findings.extend(analyze_dockerfile(dockerfile_text, source_file=source_file))
        findings.extend(
            analyze_referenced_build_scripts(
                str(root),
                dockerfile_text,
                source_file=source_file,
            )
        )

        restart_value = str(service.get("restart") or "").strip().lower()
        restart_policy = {
            "always": {"condition": "any"},
            "unless-stopped": {"condition": "any"},
            "on-failure": {"condition": "on-failure"},
            "no": {"condition": "none"},
        }.get(restart_value)
        runtime: dict[str, Any] = {
            "environment": env,
            "build_args": build_args,
            "restart_policy": restart_policy or {},
            "command": _command(service.get("command"), "command"),
            "entrypoint": _command(service.get("entrypoint"), "entrypoint"),
            "working_directory": service.get("working_dir"),
            "read_only": bool(service.get("read_only", False)),
            "labels": {},
            "public": False,
        }

        raw_labels = service.get("labels") or {}
        label_items = (
            list(raw_labels.items())
            if isinstance(raw_labels, dict)
            else [
                (str(item).split("=", 1)[0], str(item).split("=", 1)[1])
                for item in raw_labels
                if isinstance(item, str) and "=" in item
            ]
        )
        for key, value in label_items:
            label = str(key)
            if label.lower().startswith(RESERVED_LABEL_PREFIXES):
                findings.append(DockerPolicyFinding(
                    "compose_reserved_label_stripped", "warning", "strip",
                    f"Removed reserved infrastructure label '{label}'.", compose_name,
                ))
            else:
                runtime["labels"][label] = str(value)

        ports = list(service.get("ports") or [])
        if ports:
            if any("/udp" in str(item).lower() for item in ports):
                findings.append(DockerPolicyFinding(
                    "compose_udp_port_unsupported", "critical", "deny",
                    "UDP port publication is not supported by the Docker application routing model.",
                    compose_name,
                ))
            raw = ports[0]
            if isinstance(raw, dict):
                if raw.get("target") in (None, ""):
                    raise DeploymentSecurityError(
                        "Compose published ports must declare an explicit target port.",
                        stage="docker_source_validation",
                    )
                target = int(raw.get("target"))
            else:
                parts = str(raw).split(":")
                target = int(parts[-1].split("/")[0])
            if not 1 <= target <= 65535:
                raise DeploymentSecurityError("Compose target port is outside 1-65535.", stage="docker_source_validation")
            runtime["port"] = target
            runtime["public"] = True
            if len(ports) > 1:
                findings.append(DockerPolicyFinding(
                    "compose_extra_ports_stripped", "warning", "strip",
                    "Only the first application port is supported; extra ports were removed.", compose_name,
                ))
        elif service.get("expose"):
            raw = list(service["expose"])[0]
            runtime["port"] = int(str(raw).split("/")[0])
            if isinstance(service.get("x-passdeployer"), dict) and service["x-passdeployer"].get("public"):
                runtime["public"] = True

        if service.get("depends_on"):
            findings.append(DockerPolicyFinding(
                "compose_depends_on_stripped", "critical", "strip",
                "Removed depends_on because Docker mode imports one application service.", compose_name,
            ))

        volumes: list[dict[str, Any]] = []
        top_volumes = document.get("volumes") or {}
        for raw in service.get("volumes") or []:
            item = _compose_volume(raw, name, findings)
            if item:
                if (
                    item["compose_name"] in top_volumes
                    and isinstance(top_volumes[item["compose_name"]], dict)
                    and top_volumes[item["compose_name"]].get("external")
                ):
                    raise DeploymentSecurityError(
                        f"External Compose volume '{item['compose_name']}' is not owned by PassDeployer.",
                        stage="docker_source_validation",
                    )
                volumes.append(item)

        health = service.get("healthcheck")
        if health:
            test = health.get("test") if isinstance(health, dict) else ""
            test_text = " ".join(str(x) for x in test) if isinstance(test, list) else str(test)
            match = re.search(r"https?://(?:127\\.0\\.0\\.1|localhost)(?::\\d+)?([^\\s\"']*)", test_text)
            if match:
                runtime["healthcheck_path"] = match.group(1) or "/"
            else:
                findings.append(DockerPolicyFinding(
                    "compose_healthcheck_stripped", "warning", "strip",
                    "Removed healthcheck because it is outside the supported HTTP readiness model.", compose_name,
                ))

        for field in ("command", "entrypoint"):
            if runtime.get(field) and RUNTIME_DOCKER_RE.search(str(runtime[field])):
                findings.append(DockerPolicyFinding(
                    "compose_dangerous_runtime_command", "critical", "deny",
                    f"Compose {field} attempts host/Docker control.", compose_name,
                ))

        return DockerSourceResolution(
            source_kind="compose",
            source_file=compose_name,
            dockerfile_text=dockerfile_text,
            runtime=runtime,
            volumes=volumes,
            findings=findings,
        )

    if dockerfile_name:
        text = (root / dockerfile_name).read_text("utf-8", errors="replace")
        if len(text.encode()) > MAX_DOCKERFILE_BYTES:
            raise DeploymentSecurityError("Dockerfile exceeds the supported size limit.", stage="docker_source_validation")
        dockerfile_findings = analyze_dockerfile(text, source_file=dockerfile_name)
        dockerfile_findings.extend(
            analyze_referenced_build_scripts(
                str(root),
                text,
                source_file=dockerfile_name,
            )
        )
        return DockerSourceResolution(
            source_kind="dockerfile",
            source_file=dockerfile_name,
            dockerfile_text=text,
            runtime={"environment": dict(environment or {}), "labels": {}, "public": False},
            findings=dockerfile_findings,
        )

    raise DeploymentSecurityError(
        "Docker platform requires Dockerfile or Compose input.",
        stage="docker_source_validation",
        details={"expected": ["Dockerfile", "docker-compose.yml", "docker-compose.yaml", "compose.yml", "compose.yaml"]},
    )
