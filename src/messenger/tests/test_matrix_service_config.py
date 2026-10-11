from __future__ import annotations

from unittest.mock import Mock, patch

from cryptography.fernet import Fernet
from django.test import SimpleTestCase, override_settings

from messenger.matrix_service import MatrixServiceError, _config, matrix_request


class MatrixServiceConfigTests(SimpleTestCase):
    def setUp(self):
        self.encryption_key = Fernet.generate_key().decode("ascii")

    def settings_for(self, **overrides):
        values = {
            "DEBUG": False,
            "MATRIX_HOMESERVER_URL": "https://matrix.example.test",
            "MATRIX_HOMESERVER_INTERNAL_URL": "",
            "MATRIX_HOMESERVER_DOMAIN": "example.test",
            "MATRIX_ADMIN_ACCESS_TOKEN": "test-admin-token",
            "MATRIX_IDENTITY_ENCRYPTION_KEY": self.encryption_key,
        }
        values.update(overrides)
        return override_settings(**values)

    def test_public_url_is_used_for_both_paths_when_internal_url_is_unset(self):
        with self.settings_for():
            server_url, client_url, domain, admin_token, _fernet = _config()

        self.assertEqual(server_url, "https://matrix.example.test")
        self.assertEqual(client_url, "https://matrix.example.test")
        self.assertEqual(domain, "example.test")
        self.assertEqual(admin_token, "test-admin-token")

    def test_private_docker_url_is_backend_only(self):
        with self.settings_for(MATRIX_HOMESERVER_INTERNAL_URL="http://synapse:8008"):
            server_url, client_url, _domain, _admin_token, _fernet = _config()

        self.assertEqual(server_url, "http://synapse:8008")
        self.assertEqual(client_url, "https://matrix.example.test")

    def test_backend_requests_use_internal_url_when_configured(self):
        response = Mock(status_code=200, content=b'{"ok": true}')
        response.json.return_value = {"ok": True}
        with self.settings_for(MATRIX_HOMESERVER_INTERNAL_URL="http://synapse:8008"):
            with patch("messenger.matrix_service.requests.request", return_value=response) as request:
                payload = matrix_request("GET", "/_matrix/client/versions", unauthenticated=True)

        self.assertEqual(payload, {"ok": True})
        self.assertEqual(
            request.call_args.kwargs["url"],
            "http://synapse:8008/_matrix/client/versions",
        )

    def test_rejects_plain_http_internal_url_with_non_private_hostname(self):
        with self.settings_for(MATRIX_HOMESERVER_INTERNAL_URL="http://matrix.example.test:8008"):
            with self.assertRaisesMessage(
                MatrixServiceError,
                "The backend Matrix URL must use HTTPS or an explicitly configured private Docker service URL.",
            ):
                _config()

    def test_public_client_url_must_remain_https_in_production(self):
        with self.settings_for(
            MATRIX_HOMESERVER_URL="http://matrix.example.test",
            MATRIX_HOMESERVER_INTERNAL_URL="http://synapse:8008",
        ):
            with self.assertRaisesMessage(
                MatrixServiceError,
                "Secure chat requires a trusted HTTPS Matrix homeserver URL for browser clients.",
            ):
                _config()
