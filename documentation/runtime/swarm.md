# Swarm Runtime

## Compilation

```text
ServiceRevision
 -> ServiceRuntimeGraph
 -> Swarm runtime compiler
 -> Docker Swarm Service
 -> Docker Task
```

The runtime graph is Docker-neutral. `deployments/core/swarm.py` translates it to Docker SDK service specifications.

## One-replica invariant

`ServiceProcess.replicas` is constrained to exactly `1`. Invalid values are rejected rather than silently clamped.

## Process mapping

Each enabled process becomes one Swarm Service:

- web -> base service name
- worker -> `<service>-worker`
- scheduler -> `<service>-scheduler`
- custom -> `<service>-<process>`

## Stop/start/restart

Stop scales managed process services to zero and persists desired state as stopped.

Start/redeploy restores one replica.

Restart is ordered:

```text
scale 0
 -> wait for zero tasks
 -> scale 1
 -> wait for readiness
```

## Labels

Services carry stable ownership labels for Service, Deploy and Process. These labels are used for routing, logs, reconciliation and cleanup.

## Health/resources/placement

Healthchecks, process resource limits and allow-listed placement constraints are compiled into Swarm service configuration.

## Images

Application images may be built locally and published to `SWARM_IMAGE_REGISTRY` for multi-node scheduling. External database images are referenced directly.

## Volumes

Local volume workloads are pinned to their data node by default in multi-node installations.

## Base runtime images

Base runtime images are resolved on the Docker daemon connected to PassDeployer before the application image is built. On a single daemon, concurrent deployments requiring the same BaseRuntimeImage share one build and wait on its `BUILDING` state.

For a multi-node Swarm, `docker_host` is part of the BaseRuntimeImage identity, so base-image sharing is **per Docker daemon**, not cluster-wide. The final application image is what must be published to `SWARM_IMAGE_REGISTRY` for multi-node scheduling. PassDeployer does not claim that a locally built base image is automatically present on every Swarm node.

Wagtail operator actions **Build / Ensure available** and **Renew / Rebuild** enqueue the same base-image Celery task used by automatic deployment. A Renew requested while another build is active is coalesced into `rebuild_requested` and runs after the active owner finishes safely.

The base-image phase has its own `base_image_build_timeout_minutes` budget (10 minutes by default). Once all required base images are READY and fingerprint-compatible, the deployment starts a fresh `deploy_timeout_minutes` application budget.
