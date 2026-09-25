"""Application readiness checks for deployed containers."""
from __future__ import annotations

import time
import urllib.error
import urllib.request
from typing import Callable, Optional

from deployments.common.exceptions import DeploymentCancelled, HealthCheckError
from .manager.container_manager import Container

DEFAULT_MIN_RUNNING_POLLS = 3
DEFAULT_EXPECTED_STATUS = (200, 204)


class DockerHealthChecker:
    def __init__(self, logger=None, *, min_running_polls: int = DEFAULT_MIN_RUNNING_POLLS):
        self.logger = logger
        self.min_running_polls = max(1, int(min_running_polls))

    def wait_until_healthy(
        self,
        container_name: str,
        *,
        timeout: int = 60,
        interval: float = 1.0,
        allow_running_without_healthcheck: bool = True,
        healthcheck_path: Optional[str] = None,
        expected_status: tuple[int, ...] = DEFAULT_EXPECTED_STATUS,
        request_timeout: float = 5.0,
        port: Optional[int] = None,
        cancel_check: Optional[Callable[[], bool]] = None,
    ) -> dict:
        """Wait for Docker health and, when configured, application readiness.

        A Docker ``running`` state is only considered sufficient when no
        application-level path was configured and the image has no Docker
        HEALTHCHECK. When ``healthcheck_path`` is set, the deployment must
        receive one of ``expected_status`` from the application before the
        replacement can become active.
        """
        start = time.monotonic()
        last_status = "unknown"
        last_probe: dict = {}
        consecutive_running = 0
        has_healthcheck: bool | None = None
        normalized_path = self._normalize_path(healthcheck_path)
        expected = tuple(expected_status or DEFAULT_EXPECTED_STATUS)

        while time.monotonic() - start <= timeout:
            self._check_cancelled(cancel_check)
            container = Container(container_name)
            status = container.status()
            last_status = status
            info = container.inspect() or {}

            if has_healthcheck is None:
                state = info.get("State") or {}
                has_healthcheck = bool(state.get("Health"))

            if status == "healthy" and not normalized_path:
                return self._success(container_name, status, docker_healthcheck=True)

            if normalized_path and status in {"running", "healthy"}:
                try:
                    probe = self._probe_http(
                        info,
                        container_name=container_name,
                        path=normalized_path,
                        port=port or self._container_port(info),
                        expected_status=expected,
                        timeout=request_timeout,
                    )
                    last_probe = probe
                    if probe["ok"]:
                        if self.logger:
                            self.logger.info(
                                "health_check",
                                f"Application readiness check for '{container_name}' succeeded.",
                                progress=92,
                                details={"readiness": probe},
                            )
                        return {
                            "status": status,
                            "ready": True,
                            "application_check": True,
                            "path": normalized_path,
                            "http_status": probe.get("http_status"),
                            "response_time_ms": probe.get("response_time_ms"),
                        }
                except OSError as exc:
                    last_probe = {
                        "ok": False,
                        "failure_type": "connection_error",
                        "error": str(exc),
                    }

            if (
                not normalized_path
                and status == "running"
                and allow_running_without_healthcheck
                and not has_healthcheck
            ):
                consecutive_running += 1
                if consecutive_running >= self.min_running_polls:
                    return self._success(
                        container_name,
                        status,
                        docker_healthcheck=False,
                        consecutive_polls=consecutive_running,
                    )
            else:
                consecutive_running = 0

            if status == "unhealthy":
                break
            time.sleep(max(0.05, interval))

        reason = self._failure_message(
            container_name,
            last_status=last_status,
            timeout=timeout,
            path=normalized_path,
            probe=last_probe,
            has_healthcheck=has_healthcheck,
        )
        details = {
            "container": container_name,
            "last_status": last_status,
            "timeout": timeout,
            "has_healthcheck": has_healthcheck,
            "consecutive_running": consecutive_running,
            "required_consecutive": self.min_running_polls,
            "healthcheck_path": normalized_path,
            "expected_status": list(expected),
            "probe": last_probe,
        }
        raise HealthCheckError(
            reason,
            stage="health_check",
            details=details,
            technical_message=reason,
            user_message=self._user_message(last_status, normalized_path, last_probe),
            code="APPLICATION_READINESS_FAILED" if normalized_path else "HEALTH_CHECK_FAILED",
            category="health_check_error",
        )

    @staticmethod
    def _normalize_path(path: Optional[str]) -> Optional[str]:
        if not path:
            return None
        path = str(path).strip()
        if not path:
            return None
        return path if path.startswith("/") else f"/{path}"

    @staticmethod
    def _container_port(info: dict) -> int:
        ports = ((info.get("NetworkSettings") or {}).get("Ports") or {})
        for binding in ports.values():
            if isinstance(binding, list) and binding:
                try:
                    return int(binding[0].get("HostPort"))
                except (AttributeError, TypeError, ValueError):
                    continue
        config = info.get("Config") or {}
        exposed = config.get("ExposedPorts") or {}
        for raw in exposed:
            try:
                return int(str(raw).split("/")[0])
            except (TypeError, ValueError):
                continue
        return 80

    @staticmethod
    def _container_ip(info: dict) -> Optional[str]:
        networks = (info.get("NetworkSettings") or {}).get("Networks") or {}
        for net in networks.values():
            ip = (net or {}).get("IPAddress")
            if ip:
                return ip
        return (info.get("NetworkSettings") or {}).get("IPAddress") or None

    def _probe_http(
        self,
        info: dict,
        *,
        container_name: str,
        path: str,
        port: int,
        expected_status: tuple[int, ...],
        timeout: float,
    ) -> dict:
        ip = self._container_ip(info)
        if not ip:
            return {"ok": False, "failure_type": "no_container_ip", "container": container_name}
        url = f"http://{ip}:{port}{path}"
        started = time.monotonic()
        try:
            with urllib.request.urlopen(url, timeout=timeout) as response:
                status = int(response.status)
                response.read(4096)
                elapsed = round((time.monotonic() - started) * 1000, 1)
                return {
                    "ok": status in expected_status,
                    "url": url,
                    "http_status": status,
                    "expected_status": list(expected_status),
                    "response_time_ms": elapsed,
                    "failure_type": None if status in expected_status else "http_status",
                }
        except urllib.error.HTTPError as exc:
            elapsed = round((time.monotonic() - started) * 1000, 1)
            return {
                "ok": False,
                "url": url,
                "http_status": int(exc.code),
                "expected_status": list(expected_status),
                "response_time_ms": elapsed,
                "failure_type": "http_status",
                "error": str(exc),
            }
        except urllib.error.URLError as exc:
            raise OSError(str(exc.reason or exc)) from exc
        except TimeoutError as exc:
            raise OSError(f"readiness request timed out after {timeout}s") from exc

    @staticmethod
    def _failure_message(container_name, *, last_status, timeout, path, probe, has_healthcheck):
        if path and probe.get("failure_type") == "http_status":
            return (
                f"Application in container '{container_name}' started but readiness endpoint "
                f"'{path}' returned HTTP {probe.get('http_status')} instead of an expected status."
            )
        if path and probe.get("failure_type") == "no_container_ip":
            return f"Container '{container_name}' started but no container network address was available for the readiness check."
        if path and probe.get("failure_type") == "connection_error":
            return f"Container '{container_name}' started but the application at '{path}' did not accept readiness connections."
        if last_status == "unhealthy":
            return f"Container '{container_name}' reported unhealthy during deployment readiness checks."
        return f"Container '{container_name}' did not become ready before the {timeout}s readiness timeout."

    @staticmethod
    def _user_message(last_status, path, probe):
        if path and probe.get("failure_type") == "http_status":
            return "The application started, but its readiness endpoint returned an unexpected HTTP response. Check the application startup logs and readiness path configuration."
        if path:
            return "The application container started, but the application did not become ready to receive traffic. Check the readiness path, port, and application startup logs."
        if last_status == "unhealthy":
            return "The application container started but failed its Docker health check. Review the container health output and application logs."
        return "The deployment container did not become ready before the readiness timeout. Check application startup logs and runtime configuration."

    def _success(self, container_name, status, *, docker_healthcheck, consecutive_polls=None):
        details = {"container_status": status, "docker_healthcheck": docker_healthcheck}
        if consecutive_polls is not None:
            details["consecutive_polls"] = consecutive_polls
        if self.logger:
            self.logger.info("health_check", f"Container '{container_name}' is ready.", progress=90, details=details)
        return {"status": status, "ready": True, "healthcheck": docker_healthcheck, **details}

    @staticmethod
    def _check_cancelled(cancel_check):
        if cancel_check is not None and cancel_check():
            raise DeploymentCancelled(
                "Deployment cancellation requested during application readiness checking.",
                stage="cancelled",
            )
