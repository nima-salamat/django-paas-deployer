import json

from django.test import RequestFactory, SimpleTestCase, override_settings

from logs.ingest_api import _parse_record, runtime_logs_ingest_apiview


class FluentBitRecordParsingTests(SimpleTestCase):
    def test_parses_docker_fluentd_metadata_and_stream(self):
        record = {
            "container_id": "a" * 64,
            "container_name": "app-example",
            "source": "stderr",
            "log": "ERROR: example\n",
            "timestamp": "2026-10-31T12:00:00.123456Z",
            "attrs": {
                "managed-by": "django-paas-deployer",
                "passdeployer.service": "4a9e0f20-65d2-4f31-9a2f-5a3e115fbd6a",
                "passdeployer.deployment": "2e5715b8-bb76-4f8a-a6d8-dcbbd7e7a182",
            },
        }

        parsed = _parse_record(record)

        self.assertIsNotNone(parsed)
        self.assertEqual(parsed["stream"], "stderr")
        self.assertEqual(parsed["message"], "ERROR: example")
        self.assertEqual(parsed["container_id"], "a" * 64)
        self.assertEqual(
            parsed["service_id"],
            "4a9e0f20-65d2-4f31-9a2f-5a3e115fbd6a",
        )

    def test_rejects_unmanaged_or_invalid_container_metadata(self):
        unmanaged = {
            "container_id": "a" * 64,
            "source": "stdout",
            "log": "hello",
            "attrs": {"managed-by": "other"},
        }
        invalid_id = {
            "container_id": "not-a-container",
            "source": "stdout",
            "log": "hello",
            "attrs": {
                "managed-by": "django-paas-deployer",
                "passdeployer.service": "4a9e0f20-65d2-4f31-9a2f-5a3e115fbd6a",
            },
        }
        self.assertIsNone(_parse_record(unmanaged))
        self.assertIsNone(_parse_record(invalid_id))


class FluentBitIngestionAuthenticationTests(SimpleTestCase):
    def setUp(self):
        self.factory = RequestFactory()

    @override_settings(LOG_INGEST_SHARED_TOKEN="test-secret")
    def test_missing_token_is_rejected(self):
        request = self.factory.post(
            "/services/internal/logs/ingest/",
            data=b"",
            content_type="application/x-ndjson",
        )
        response = runtime_logs_ingest_apiview(request)
        self.assertEqual(response.status_code, 401)

    @override_settings(LOG_INGEST_SHARED_TOKEN="test-secret")
    def test_valid_token_can_send_empty_health_batch(self):
        request = self.factory.post(
            "/services/internal/logs/ingest/",
            data=b"",
            content_type="application/x-ndjson",
            HTTP_X_PASSDEPLOYER_TOKEN="test-secret",
        )
        response = runtime_logs_ingest_apiview(request)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(json.loads(response.content), {
            "result": "success",
            "accepted": 0,
            "rejected": 0,
        })
