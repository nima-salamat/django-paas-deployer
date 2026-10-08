from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import Mock

import pytest

pytestmark = pytest.mark.deployment_integration


def test_build_cache_usage_parses_current_shape():
    from deploy import build_cache

    class FakeApi:
        def df(self):
            return {"BuildCacheUsage": {"TotalSize": 4096, "Reclaimable": 2048, "ActiveCount": 2, "TotalCount": 5}}

    client = SimpleNamespace(api=FakeApi())
    assert build_cache.get_global_build_cache_usage(client) == {
        "total_size": 4096,
        "reclaimable": 2048,
        "active_count": 2,
        "total_count": 5,
    }


def test_build_cache_global_limit_prunes_with_storage_target(monkeypatch):
    from deploy import build_cache

    monkeypatch.setattr(
        build_cache,
        "build_cache_policy",
        lambda: {
            "enabled": True,
            "global_limit_mb": 10,
            "user_quota_mb": 5,
            "service_quota_mb": 2,
            "retention_days": 0,
            "keep_successful_deployments": 3,
            "cleanup_target_percent": 80,
            "batch_size": 50,
        },
    )
    usage = iter([
        {"total_size": 12 * 1024 * 1024, "reclaimable": 8, "active_count": 1, "total_count": 3},
        {"total_size": 12 * 1024 * 1024, "reclaimable": 8, "active_count": 1, "total_count": 3},
        {"total_size": 9 * 1024 * 1024, "reclaimable": 1, "active_count": 1, "total_count": 2},
    ])
    monkeypatch.setattr(build_cache, "get_global_build_cache_usage", lambda client=None: next(usage))
    api = Mock()
    api.prune_builds.return_value = {"CachesDeleted": ["a"], "SpaceReclaimed": 3}
    client = SimpleNamespace(api=api)

    result = build_cache.prune_global_build_cache(client=client)
    assert result["status"] == "cleaned"
    assert api.prune_builds.call_args.kwargs["keep_storage"] == 8 * 1024 * 1024


def test_build_cache_retention_uses_engine_duration(monkeypatch):
    from deploy import build_cache

    monkeypatch.setattr(
        build_cache,
        "build_cache_policy",
        lambda: {
            "enabled": True,
            "global_limit_mb": 1024,
            "user_quota_mb": 512,
            "service_quota_mb": 256,
            "retention_days": 30,
            "keep_successful_deployments": 3,
            "cleanup_target_percent": 80,
            "batch_size": 50,
        },
    )
    usage = iter([
        {"total_size": 1, "reclaimable": 1, "active_count": 1, "total_count": 1},
        {"total_size": 1, "reclaimable": 1, "active_count": 1, "total_count": 1},
        {"total_size": 1, "reclaimable": 1, "active_count": 1, "total_count": 1},
    ])
    monkeypatch.setattr(build_cache, "get_global_build_cache_usage", lambda client=None: next(usage))
    api = Mock()
    api.prune_builds.return_value = {"CachesDeleted": [], "SpaceReclaimed": 0}
    client = SimpleNamespace(api=api)

    result = build_cache.prune_global_build_cache(client=client)

    assert result["status"] == "cleaned"
    assert api.prune_builds.call_args_list[0].kwargs["filters"] == {"until": "720h"}

def test_build_cache_quota_requires_exactly_one_owner():
    from deploy.models import BuildCacheQuota
    from django.core.exceptions import ValidationError

    with pytest.raises(ValidationError):
        BuildCacheQuota().full_clean()
