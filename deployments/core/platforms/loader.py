"""
Import all platform plugins so they register themselves
with PlatformRegistry via the @PlatformRegistry.register decorator.
"""

# Node family
from .node import (  # noqa: F401
    NodePlatform,
    ReactPlatform,
    NextPlatform,
    VitePlatform,
    VuePlatform,
    AngularPlatform,
    ExpressPlatform,
)

# Python family
from .python import (  # noqa: F401
    PythonPlatform,
    DjangoPlatform,
    FlaskPlatform,
    FastAPIPlatform,
)

# PHP family
from .php import PHPPlatform, LaravelPlatform  # noqa: F401

# Go
from .go import GoPlatform  # noqa: F401

# Static
from .static import StaticPlatform  # noqa: F401

# Generic fallback
from .generic import GenericPlatform  # noqa: F401
