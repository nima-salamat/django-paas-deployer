"""
deployments/core/state/__init__.py
----------------------------------
State management package — explicit transition validation + locking.
"""

from .locks import DeploymentLock, acquire_service_deployment_lock
from .manager import StateManager

__all__ = ["DeploymentLock", "acquire_service_deployment_lock", "StateManager"]
