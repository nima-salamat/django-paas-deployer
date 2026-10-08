import unittest
from datetime import timedelta
from types import SimpleNamespace

from django.utils import timezone

from logs.ingestion import lease_is_current


class LogLeaseAuthorityTests(unittest.TestCase):
    def test_current_owner_with_live_lease_is_valid(self):
        now = timezone.now()
        stream = SimpleNamespace(owner_id="collector-a", lease_until=now + timedelta(seconds=10))
        self.assertTrue(lease_is_current(stream, "collector-a", now=now))

    def test_different_owner_is_never_valid(self):
        now = timezone.now()
        stream = SimpleNamespace(owner_id="collector-a", lease_until=now + timedelta(seconds=10))
        self.assertFalse(lease_is_current(stream, "collector-b", now=now))

    def test_expired_lease_is_not_valid(self):
        now = timezone.now()
        stream = SimpleNamespace(owner_id="collector-a", lease_until=now - timedelta(seconds=1))
        self.assertFalse(lease_is_current(stream, "collector-a", now=now))


if __name__ == "__main__":
    unittest.main()
