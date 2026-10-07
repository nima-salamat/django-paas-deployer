"""Pure planning and configuration-resolution primitives."""

from .configuration import (
    ConfigurationLayer,
    ConfigurationResolutionError,
    ConfigurationResolver,
    ResolvedConfiguration,
)
from .plan import DeploymentPlan, DeploymentPlanCompiler
from .runtime_spec import RuntimeSpec
from .provenance import ConfigurationProvenance, ProvenanceRecord
from .bridge import DeploymentPlanCompatibilityCompiler

from .policies import HealthPolicy, ReleaseSpec, RolloutStrategy

__all__ = [
    "HealthPolicy",
    "ReleaseSpec",
    "RolloutStrategy",
    "ConfigurationLayer",
    "ConfigurationProvenance",
    "ConfigurationResolutionError",
    "ConfigurationResolver",
    "DeploymentPlan",
    "DeploymentPlanCompiler",
    "RuntimeSpec",
    "DeploymentPlanCompatibilityCompiler",
    "ProvenanceRecord",
    "ResolvedConfiguration",
]

__all__ = [*globals().get("__all__", []), "HealthPolicy", "ReleaseSpec", "RolloutStrategy"]
