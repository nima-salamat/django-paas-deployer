"""Runtime contracts and adapters for deployment execution.

The runtime package is intentionally dependency-light.  Domain and planning
code should depend on these value objects and protocols rather than on a
Docker SDK client or a concrete Swarm implementation.
"""

from .capabilities import (
    RuntimeAvailability,
    RuntimeAvailabilityState,
    RuntimeCapabilities,
    RuntimeCapability,
)
from .contract import (
    RuntimeBackend,
    RuntimeHandle,
    RuntimeIdentity,
    RuntimeOperationResult,
    RuntimeSelection,
)
from .errors import (
    RuntimeOperationError,
    RuntimeUnavailableError,
    RuntimeUnsupportedError,
)
from .registry import RuntimeRegistry

__all__ = [
    "RuntimeAvailability",
    "RuntimeAvailabilityState",
    "RuntimeBackend",
    "RuntimeCapabilities",
    "RuntimeCapability",
    "RuntimeHandle",
    "RuntimeIdentity",
    "RuntimeOperationResult",
    "RuntimeOperationError",
    "RuntimeRegistry",
    "RuntimeSelection",
    "RuntimeUnavailableError",
    "RuntimeUnsupportedError",
]
