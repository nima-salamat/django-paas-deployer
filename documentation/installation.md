# Installation

This guide describes deployment of the PassDeployer control plane and Docker runtime dependencies.

For multi-node Swarm, local persistent volumes are provisioned through the Django volume registry and pinned to the provisioning node. A conflicting explicit node.id placement rule is rejected for managed local volumes.

Tenant storage quota is a logical Service policy; standard Docker local volumes do not provide a hard per-volume filesystem quota. Runtime usage is measured when the Docker backend can report it and warnings follow operator settings.

Canonical storage/domain semantics are now under [apps/services/models.md](apps/services/models.md) and the deep runtime discussion in [deployments/05-runtime-and-swarm.md](deployments/05-runtime-and-swarm.md).

## Legacy mode

SWARM_ENABLED=0 remains an explicit compatibility mode. The normal architecture is Swarm-first.
