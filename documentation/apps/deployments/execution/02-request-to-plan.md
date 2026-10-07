# 02 — Request to plan

## Purpose

Explain how a deployment request becomes a normalized execution description.

The central reasoning boundary is:

```text
mutable request
   ->
immutable revision
   ->
resolved configuration
   ->
platform interpretation
   ->
runtime graph
   ->
DeploymentPlan
   ->
current compatibility DTO
```

## Current production path

`DeployService._process_deployment()` is the key composition point in the current master path.

It:

1. materializes the revision;
2. normalizes the legacy/public profile;
3. determines the execution family from the Service Plan;
4. refines PHP/Python framework aliases;
5. prepares platform/detection values;
6. validates tenant customizations;
7. obtains Dockerfile text;
8. validates the deployment;
9. calls the orchestrator composition path.

## How revisioning is used

**Called by:** `DeployService._execute_locked()`.

**Preconditions:** Deploy and Service are locked appropriately; execution ownership exists.

**Input:** mutable Service state plus legacy Deploy input when needed.

**Output:** immutable ServiceRevision.

**Next:** `materialize_revision_config()` and `ServiceRuntimeGraph.from_revision()`.

**Why:** no long-running Docker build should depend on mutable Service rows.

## Configuration parsing

**Module:** `deployments.common.config`

### Contract

`parse_config()` normalizes:

- dict;
- JSON string;
- double-encoded JSON string;

into a dictionary. Invalid/empty input becomes an empty dict.

### Use

It is a compatibility parser, not the policy resolver.

### Must not

Do not add resource/security policy to `parse_config()` merely because the raw key is available there.

## Profile normalization

**Module:** `deployments.common.deployment_profile`

### Called by

Current `DeployService._process_deployment()`.

### Input

The revision-materialized config or legacy Deploy.config.

### Output

Normalized public/deployment profile with:

- build_options;
- runtime_options;
- frontend options;
- safe aliases.

Tenant resource-limit and worker-count overrides are deliberately removed/ignored.

### Why

The public config format should be ergonomic without becoming an authority for host resource allocation.

## ConfigurationResolver

**Module:** `deployments/planning/configuration.py`

### What it owns

Layer precedence and provenance.

The resolver contract is:

```text
platform_defaults
   < platform_policy
   < cluster_policy
   < service_intent
   < revision_snapshot
   < permitted deployment overrides
```

The resolver records the effective source for each path and rejects deployment override paths outside its allow-list.

It also checks policy ceilings such as replica limits.

### Current production usage

Do not overstate this contract.

The current DeployService uses `ConfigurationResolver` inside `_compile_native_plan()`, where it supplies a **subset** of the possible layers: platform-policy resource limits and a revision-snapshot-like set of environment/runtime/network/volume/endpoint/health values.

The main path still performs additional concrete normalization in `_process_deployment()` before the native plan is compiled.

### How it is used

**Called by:** current plan compatibility compiler.

**Preconditions:** inputs are already normalized enough to be represented as configuration layers.

**Output:** `ResolvedConfiguration` + `ConfigurationProvenance`.

**Consumer:** `DeploymentPlanCompiler`.

**Failure:** `ConfigurationResolutionError` for forbidden overrides/invalid policy values.

### Why

Without a dedicated resolver, precedence appears as scattered “if value else default” expressions and cannot be explained or tested independently.

### Anti-pattern

Do not make runtime code re-resolve the same setting from the database. Once the plan boundary is adopted, runtime should consume the resolved value.

## Platform detection

**Modules:** `core/platforms/inspector.py`, `registry.py`, `base/platform.py`.

The actual flow:

```text
project archive
   ->
safe extraction
   ->
ProjectInspector.scan()
   ->
every registered plugin detect()
   ->
DetectionResult candidates
   ->
preferred platform if explicitly requested
   OR highest confidence / priority
   ->
selected plugin.resolve()
   ->
ProjectConfig
```

### Inspector contract

**Input:** project root.

**Output:** bounded file index, directory index and marker information.

**Must not:** Docker calls or lifecycle mutations.

### PlatformRegistry contract

**Preconditions:** plugins are registered.

**Output:** selected plugin, DetectionResult, ProjectConfig.

**Decision rule:** explicit preferred platform wins when a matching plugin exists; otherwise confidence then plugin priority.

**Fallback:** generic plugin if no detector matches.

### BasePlatform contract

Each plugin supplies:

- `detect()`;
- `defaults()`;
- `inspect()`;

and inherits:

- `resolve()`;
- schema validation;
- safe file helpers.

The merge inside a plugin is:

```text
platform defaults
   < auto-detection
   < user_config
```

This is **source interpretation**, not host infrastructure policy.

### Why detection and policy are separate

Detection answers “what does this project look like?”

Configuration policy answers “what values are allowed/effective?”

Mixing them makes a framework plugin an accidental security/runtime-policy owner.

## Framework refinement

The current `DeployService` path takes the Service Plan as the execution-family authority and allows compatible framework refinement.

For example:

```text
plan.platform = php
config/framework = laravel
        ->
effective platform = laravel
```

This is intentionally narrower than “tenant may choose any runtime”.

## Runtime selection

**Module:** `deployments/runtime/registry.py`

### Inputs

Policy/cluster context and optional capability requirements.

### It deliberately ignores

Service/Revision/Deploy backend fields.

### Why

Host infrastructure must remain operator-controlled.

### Selection sources

1. deployment/cluster policy;
2. `DEPLOYMENT_RUNTIME_BACKEND`;
3. `SWARM_ENABLED` as compatibility input;
4. Swarm default.

### Output

`RuntimeSelection`.

If `probe=True`, availability is checked by the adapter; otherwise availability may remain UNKNOWN.

## ServiceRuntimeGraph

**Module:** `core/runtime_graph.py`.

### Called by

DeployService after revision materialization.

### Input

ServiceRevision.

### Output

Processes, endpoints, network and volume semantics plus runtime/build metadata.

### Why

This is the compact runtime-semantic model that prevents Docker SDK objects from leaking upward.

### Consumer

DeploymentPlanCompiler and current compatibility DTO composition.

## DeploymentPlanCompiler

**Module:** `planning/plan.py`.

### Inputs

- RuntimeIdentity;
- ServiceRuntimeGraph;
- RuntimeSelection;
- ResolvedConfiguration;
- image reference;
- strategy kind.

### Preconditions

- image ref is non-empty;
- strategy kind is application/database/specialized;
- selected runtime can satisfy required capabilities.

### Output

Frozen `DeploymentPlan`.

### Capability derivation

The compiler always requires service scheduling and process graph support. It adds capabilities for replicas, persistent volumes, overlay networks, health checks and placement when the graph/config needs them.

### Why

A plan should fail before runtime work if the selected backend cannot represent the requested topology.

## Compatibility bridge

**Module:** `planning/bridge.py`.

### Called by

Current `core/deploy.py::Deploy._config()`.

### Input

DeploymentPlan + existing DeploymentConfig.

### Output

DeploymentConfig with plan-derived environment/networks/volumes/endpoints/resources/labels/placement and supported Docker healthcheck fields.

### Why

It lets the new plan boundary feed the old orchestrator without pretending the old orchestrator has already disappeared.

### Anti-pattern

Do not use the bridge as a reason to bypass plan compilation.

## Decision ownership

```text
Service/domain
  -> what user wants

Revisioning
  -> what this execution freezes

ConfigurationResolver
  -> what layered policy makes effective

Platform layer
  -> what the source tree means

DeploymentPlanCompiler
  -> whether effective runtime semantics are representable

Orchestrator/runtime
  -> how to make infrastructure match the effective plan

StateManager
  -> whether lifecycle state may advance
```

## Modification guidance

- Change tenant config vocabulary -> `common/config.py` + profile/config tests.
- Change precedence/provenance -> `planning/configuration.py`.
- Change framework detection -> plugin/registry.
- Change process/topology semantics -> revisioning/runtime graph.
- Change runtime capability validation -> DeploymentPlanCompiler.
- Change Docker behavior -> runtime/orchestrator, not planning.

