"""Pure planning and configuration-resolution primitives."""

from .configuration import (
    ConfigurationLayer,
    ConfigurationResolutionError,
    ConfigurationResolver,
    ResolvedConfiguration,
)
from .plan import DeploymentPlan, DeploymentPlanCompiler
from .provenance import ConfigurationProvenance, ProvenanceRecord
from .bridge import DeploymentPlanCompatibilityCompiler

__all__ = [
    "ConfigurationLayer",
    "ConfigurationProvenance",
    "ConfigurationResolutionError",
    "ConfigurationResolver",
    "DeploymentPlan",
    "DeploymentPlanCompiler",
    "DeploymentPlanCompatibilityCompiler",
    "ProvenanceRecord",
    "ResolvedConfiguration",
]
