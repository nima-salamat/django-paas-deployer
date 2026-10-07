
import tempfile

import pytest

from deployments.core.platforms.registry import (
    PlatformDetectionPolicyError,
    PlatformRegistry,
)


def test_generic_fallback_requires_explicit_platform_for_automatic_selection():
    with tempfile.TemporaryDirectory() as root:
        with pytest.raises(PlatformDetectionPolicyError):
            PlatformRegistry.detect(root, preferred_platform=None)


def test_explicit_generic_platform_remains_supported():
    with tempfile.TemporaryDirectory() as root:
        plugin, result, config = PlatformRegistry.detect(
            root,
            preferred_platform="generic",
        )
        assert plugin.name == "generic"
        assert result.confidence == 0.05
        assert config.platform == "generic"
