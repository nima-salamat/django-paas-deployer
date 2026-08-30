import logging
import unittest

from deployments.common.build_slots import BuildSlot
from deployments.core.types import DeploymentConfig


class DeploymentContractRegressionTests(unittest.TestCase):
    def test_config_accepts_detection_static_dir(self):
        cfg = DeploymentConfig(
            name="app", tag="x", zip_path="/tmp/x.zip", dockerfile_template="FROM alpine",
            max_cpu=1, max_ram=512, networks=[], volumes=[], port=80, read_only=False,
            platform="php", platform_type="APP", static_dir="public", media_dir="storage",
        )
        self.assertEqual(cfg.static_dir, "public")

    def test_build_slot_logger_fallback_does_not_use_details_kwarg(self):
        class FakeRedis:
            def set(self, *args, **kwargs): return True
            def eval(self, *args): return 1

        import deployments.common.build_slots as slots
        old = slots._redis_client
        try:
            slots._redis_client = lambda: FakeRedis()
            with BuildSlot(deployment_id="regression", logger=logging.getLogger("regression")):
                pass
        finally:
            slots._redis_client = old
