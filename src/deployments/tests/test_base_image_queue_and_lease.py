from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def test_base_image_task_is_not_consumed_by_deployment_worker():
    compose = ROOT.parent.joinpath("compose.yaml").read_text(encoding="utf-8")
    deployment = compose.split("deployment-worker:", 1)[1].split("base-image-worker:", 1)[0]
    base_worker = compose.split("base-image-worker:", 1)[1]
    assert "-Q" in base_worker and "base-images" in base_worker
    assert "base-images" not in deployment


def test_long_running_build_slot_renews_the_same_token(monkeypatch):
    import deployments.common.build_slots as slots

    class FakeRedis:
        def __init__(self):
            self.owner = None
            self.expiry = 0
            self.renewals = 0
        def set(self, key, token, nx=False, ex=None):
            if self.owner is None:
                self.owner = token
                self.expiry = int(ex)
                return True
            return False
        def eval(self, script, numkeys, key, token, value=None):
            if "expire" in script:
                if self.owner == token:
                    self.expiry = int(value)
                    self.renewals += 1
                    return 1
                return 0
            if self.owner == token:
                self.owner = None
                return 1
            return 0

    fake = FakeRedis()
    monkeypatch.setattr(slots, "_redis_client", lambda: fake)
    monkeypatch.setattr(slots, "_parallelism", lambda: 1)
    monkeypatch.setattr(slots, "_lease_seconds", lambda: 60)
    monkeypatch.setattr(slots, "_wait_seconds", lambda: 5)

    slot = slots.BuildSlot(deployment_id="long-build")
    slot.__enter__()
    try:
        for _ in range(20):
            assert slot._renew_lease()
            assert fake.owner == slot.token
        assert fake.renewals == 20
        slot.assert_owned()
    finally:
        slot.__exit__(None, None, None)
