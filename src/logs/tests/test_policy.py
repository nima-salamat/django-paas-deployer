
from django.test import SimpleTestCase
from logs.policy import EffectiveLoggingPolicy, resolve


class _Plan:
    log_retention_days = 7
    log_storage_mb = 100
    log_ingest_bytes_per_sec = 50000
    persistent_logging = True
    realtime_logging = True
    log_quota_behavior = "fifo_delete"


class _Service:
    plan = _Plan()


class PolicyTests(SimpleTestCase):
    def test_resolve_returns_policy(self):
        # Without DB settings, still returns dataclass
        p = resolve(_Service())
        self.assertIsInstance(p, EffectiveLoggingPolicy)
        self.assertGreaterEqual(p.retention_days, 1)
        self.assertGreater(p.storage_quota_bytes, 0)
