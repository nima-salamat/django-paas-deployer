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
