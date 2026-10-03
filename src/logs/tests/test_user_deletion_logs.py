from django.test import TestCase, override_settings
from django.utils import timezone

from deploy.models import DeployLog
from logs.models import LogUsageDaily, ServiceLogEntry, ServiceLogStream, ServiceLogUsage
from services.signals import _cleanup_service_log_records


class LogUserDeletionTests(TestCase):
    @override_settings(DEPLOYMENT_LOG_DB_ALIAS="default")
    def test_service_log_cleanup_removes_scalar_user_service_records(self):
        service_id = "11111111-1111-4111-8111-111111111111"
        stream = ServiceLogStream.objects.create(
            service_id=service_id,
            container_id="container",
            container_name="container",
        )
        ServiceLogEntry.objects.create(
            service_id=service_id,
            stream_id=stream.pk,
            ts=timezone.now(),
            seq=1,
            stream=ServiceLogEntry.StreamKind.STDOUT,
            message="line",
            byte_size=4,
            fingerprint="f" * 64,
        )
        ServiceLogUsage.objects.create(
            service_id=service_id,
            current_storage_bytes=4,
            entry_count=1,
        )
        LogUsageDaily.objects.create(
            service_id=service_id,
            date=timezone.now().date(),
            bytes_ingested=4,
            entries_ingested=1,
        )
        DeployLog.objects.create(
            deploy_id=service_id,
            service_id=service_id,
            stage="test",
            event_type="test",
            message="event",
        )

        deleted = _cleanup_service_log_records(service_id)

        self.assertGreaterEqual(deleted["runtime_log_entries"], 1)
        self.assertFalse(ServiceLogStream.objects.filter(pk=stream.pk).exists())
        self.assertFalse(ServiceLogEntry.objects.filter(service_id=service_id).exists())
        self.assertFalse(ServiceLogUsage.objects.filter(service_id=service_id).exists())
        self.assertFalse(LogUsageDaily.objects.filter(service_id=service_id).exists())
        self.assertFalse(DeployLog.objects.filter(service_id=service_id).exists())
