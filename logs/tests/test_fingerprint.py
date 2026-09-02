
from django.test import SimpleTestCase
from django.utils import timezone
from logs.ingestion import fingerprint


class FingerprintTests(SimpleTestCase):
    def test_stable(self):
        ts = timezone.now()
        a = fingerprint(ts, "stdout", "hello")
        b = fingerprint(ts, "stdout", "hello")
        self.assertEqual(a, b)
        self.assertNotEqual(a, fingerprint(ts, "stderr", "hello"))
