# 02 — Request to plan

## Purpose

Explain how mutable configuration becomes the normalized input used by deployment execution. The invariant is that tenant intent is resolved and snapshotted before infrastructure work relies on it.

## Current transformation

~~~text
API/service request
    -> Deploy row
    -> ensure_revision_for_deploy()
    -> revision snapshots
    -> materialize_revision_config()
    -> normalize_profile()/parse_config()
    -> platform detection + project enrichment
    -> runtime/resource policy
    -> runtime graph
    -> DeploymentPlan
    -> transitional bridge
    -> DeploymentConfig
~~~

The last two steps are transitional on current master: the application path still executes through the legacy-shaped DeploymentConfig consumed by DeploymentOrchestrator.

## 1. Request and Deploy creation

The API/service layer creates a Deploy and queues the appropriate Celery operation. A queued Deploy is execution intent, not yet the immutable source of truth.

Deployment tasks must not assume that Deploy.config remains the final runtime configuration.

## 2. Revision materialization

services.revisioning.ensure_revision_for_deploy() runs under a transaction and locks the Deploy and Service.

It merges the relevant legacy Deploy input with Service-owned source/build/runtime state, normalizes environment/process/endpoint/volume/network snapshots, versions secrets, and creates an immutable ServiceRevision.

The deployment artifact is copied into revision-owned storage where applicable so a later rollback does not depend on the mutable Deploy upload.

After this point the normal application deployment path treats the revision as executable source of truth. Deploy.config remains for compatibility and migration.

## 3. Configuration parsing and normalization

deployments.common.config.parse_config() is the shared parser for old/new representations of Deploy.config.

deployments.common.deployment_profile.normalize_profile() converts legacy flat keys and nested build/runtime profiles into normalized build_options and runtime_options.

It also removes tenant-controlled resource fields from the public deployment profile. Runtime resources are derived from the Service Plan and build resources from operator-owned policy.

This is a critical security boundary:

- tenant configuration can refine allowed application behavior;
- tenant configuration cannot choose arbitrary Docker host settings, resource limits, devices, network mode, host binds, privileged mode, or worker count.

## 4. Configuration precedence

The newer ConfigurationResolver in deployments/planning/configuration.py makes precedence explicit:

~~~text
platform defaults
    < platform policy
    < cluster policy
    < service intent
    < revision snapshot
    < permitted deployment overrides
~~~

Deployment-request overrides are restricted to an allow-list. Attempts to override operator-owned policy are rejected with ConfigurationResolutionError.

The resolver records provenance in ConfigurationProvenance, and public values are redacted for sensitive keys.

The current DeployService path still performs some compatibility normalization directly. Do not claim that every current deployment goes exclusively through ConfigurationResolver; it is the explicit planning boundary being adopted.

## 5. Platform and framework detection

The current detector pipeline is:

~~~text
ZIP/project tree
 -> ProjectInspector
 -> PlatformRegistry.detect()
 -> candidate DetectionResult values
 -> highest confidence / plugin priority
 -> ProjectConfig
 -> deployment config enrichment
~~~

ProjectInspector builds a bounded file/directory index and known marker list.

PlatformRegistry runs every registered plugin, honors an explicit preferred platform when present, otherwise picks by confidence then plugin priority, and falls back to the generic plugin.

User/framework configuration may refine the detected result, but the plan/platform family remains the architectural control boundary.

## 6. Runtime selection

deployments.runtime.RuntimeRegistry resolves the backend from operator or cluster policy.

The registry intentionally does not consult Service/Revision/Deploy tenant fields to choose host infrastructure.

Selection sources are operator policy, cluster policy, DEPLOYMENT_RUNTIME_BACKEND, SWARM_ENABLED as legacy compatibility input, then the Swarm default.

Capabilities and availability are separate concepts.

## 7. Resource policy

Runtime resources are taken from the selected Service Plan through runtime_limits().

Build resources are resolved by resource_policy.build_limits()/resolve_build_policy() from operator settings, optionally constrained by operator plan build mode.

A future model must not add tenant resource knobs merely because an old config field exists.

## 8. Runtime graph and plan

ServiceRuntimeGraph compiles process, endpoint, network, volume and runtime metadata.

DeploymentPlanCompiler requires an image reference, validates strategy kind, derives required runtime capabilities, and produces an immutable plan.

Required capabilities include process scheduling; graph-dependent capabilities include replicas, persistent volumes, overlay networks, health checks and node constraints.

## 9. Current compatibility bridge

DeploymentPlanCompatibilityCompiler converts a DeploymentPlan into the existing DeploymentConfig DTO.

It translates placement, selected Docker healthcheck fields, labels, environment, network/volume/endpoint lists and resource limits.

This class is deliberately a compatibility boundary. It does not mean callers should bypass planning.

## 10. Decision ownership

~~~text
API/service layer
  owns: user intent and request validation

revisioning
  owns: immutable executable snapshot

planning
  owns: normalization, policy resolution, capabilities, provenance

platform plugins
  own: source inspection and framework-specific defaults/detection

orchestrator/runtime
  owns: Docker/Swarm execution

state manager
  owns: persisted lifecycle transitions
~~~

A layer must not move decisions down simply because the information is available there.

## Failure behavior

- Invalid request/configuration: fail before infrastructure mutation.
- Forbidden configuration override: reject.
- Revision materialization failure: no executable snapshot is accepted.
- Missing runtime capability: runtime selection/plan compilation fails.
- Internal implementation exceptions: converted to non-recoverable deployment errors at the task boundary.

## Related code

- src/services/revisioning.py
- src/deployments/common/config.py
- src/deployments/common/deployment_profile.py
- src/deployments/planning/configuration.py
- src/deployments/planning/plan.py
- src/deployments/planning/bridge.py
- src/deployments/core/platforms/registry.py
- src/deployments/runtime/registry.py
- src/deployments/core/runtime_graph.py
