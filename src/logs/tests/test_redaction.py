from unittest.mock import patch

from django.test import SimpleTestCase

from deployments.common.security import redact_secrets
from logs.ingestion import _redact


class RuntimeLogRedactionTests(SimpleTestCase):
    def test_authorization_bearer_token_is_removed(self):
        raw = "Authorization: Bearer eyJhbGciOi.example.signature"
        redacted = redact_secrets(raw)
        self.assertNotIn("eyJhbGciOi", redacted)
        self.assertIn("***REDACTED***", redacted)

    def test_quoted_password_and_url_credentials_are_removed(self):
        raw = 'password="my-secret" postgres://app:db-secret@db.example/app'
        redacted = redact_secrets(raw)
        self.assertNotIn("my-secret", redacted)
        self.assertNotIn("db-secret", redacted)

    def test_redaction_error_never_returns_raw_message(self):
        with patch(
            "deployments.common.security.redact_secrets",
            side_effect=RuntimeError("redactor unavailable"),
        ):
            with self.assertRaises(RuntimeError):
                _redact("password=must-not-be-stored")
