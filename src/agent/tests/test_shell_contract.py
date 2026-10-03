from django.core.exceptions import ValidationError as DjangoValidationError
from django.test import SimpleTestCase


class AgentShellContractTests(SimpleTestCase):
    def test_shell_policy_error_is_normalized_without_a_drf_response(self):
        from agent.errors import normalize_exception

        exc = DjangoValidationError(
            "A command in this sequence is classified as destructive and requires confirmation."
        )
        exc.shell_code = "CONFIRMATION_REQUIRED"

        response = normalize_exception(exc, None)

        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.data["result"], "error")
        self.assertEqual(response.data["code"], "CONFIRMATION_REQUIRED")
        self.assertEqual(response.data["failure_domain"], "authorization")
        self.assertFalse(response.data["retryable"])

    def test_generic_missing_response_is_still_structured(self):
        from agent.errors import normalize_exception

        response = normalize_exception(RuntimeError("boom"), None)

        self.assertEqual(response.status_code, 500)
        self.assertEqual(response.data["result"], "error")
        self.assertEqual(response.data["code"], "INTERNAL_ERROR")
        self.assertEqual(response.data["failure_domain"], "runtime")
