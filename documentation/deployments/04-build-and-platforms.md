# 04 — Build and platforms

## Purpose

This document explains how source code is interpreted and turned into an application image. It deliberately separates project interpretation, policy resolution, image construction and runtime.

## Information flow

~~~text
ZIP
 |
 v
safe extraction
 |
 v
ProjectInspector
 |
 v
DetectionResult candidates
 |
 v
selected platform plugin
 |
 v
ProjectConfig
 |
 v
DeployService / planning normalization
 |
 v
DockerfileGenerator inputs
 |
 +---- BaseRuntimeImage
 |
 v
application image
 |
 v
runtime configuration
~~~

## ProjectInspector

**Path:** \`core/platforms/inspector.py\`

### Called by

\`PlatformRegistry.detect()\`.

### Input

Extracted project root.

### Output

Bounded file/directory indexes and marker information.

### Why bounded

The archive is untrusted input. Detection should inspect enough structure to classify the project without recursively indexing dependency/cache trees unnecessarily.

### Must not

- call Docker;
- build images;
- mutate deployment state.

## PlatformRegistry

**Path:** \`core/platforms/registry.py\`

### Called by

\`core/platform_bridge.py::enrich_config_from_project()\`.

### Preconditions

Plugins loaded, project root extracted.

### Output

\`(plugin, DetectionResult, ProjectConfig)\`.

### Decision algorithm

1. scan source tree;
2. run every registered detector;
3. if an explicit preferred platform matches, use it;
4. otherwise sort by confidence and plugin priority;
5. generic fallback if needed;
6. resolve the selected plugin's configuration.

### Why confidence and priority are separate

Confidence expresses evidence from the source tree. Priority is a deterministic tie-breaker between equally confident plugins.

## BasePlatform contract

**Path:** \`core/platforms/base/platform.py\`

A plugin supplies source interpretation.

### \`detect(file_index)\`

**Input:** inspector file index.

**Output:** DetectionResult or None.

**Must not:** mutate state or perform infrastructure calls.

### \`defaults()\`

Lowest-priority platform defaults.

### \`inspect(file_index)\`

Extracts concrete project facts such as runtime version, entrypoint or build directory.

### \`resolve()\`

Combines:

~~~text
platform defaults
    < auto-detected values
    < user_config
~~~

and produces ProjectConfig plus source provenance.

### \`validate()\`

Validates the resolved ProjectConfig against the platform schema.

### Why plugins own this

A framework detector should know how Django, Laravel, React, etc. reveal themselves. It should not know which Swarm node to use or which DB row is authoritative.

## Current registered plugin families

The current loader registers:

- Node: Node, React, Next, Vite, Vue, Angular, Express;
- Python: Python, Django, Flask, FastAPI;
- PHP: PHP, Laravel;
- Other: Go, Static, Generic.

Use \`core/platforms/loader.py\` as the exact registry source before documenting a new framework.

## Platform bridge

**Path:** \`core/platform_bridge.py\`

### Called by

\`DeploymentOrchestrator.deploy()\` during source extraction/build preparation.

### Input

DeploymentConfig + extracted project root.

### Output

Same DeploymentConfig enriched with empty fields from platform detection.

### Important precedence

Existing caller values remain higher priority than auto-detection. Detection is used to fill missing values.

### Important special case

The bridge intentionally does not promote certain detected start commands into entry_point for SPA/Nginx and PHP-family images, because doing so can suppress renderer-owned commands such as Apache startup or frontend build injection.

### Why this guard exists

The Dockerfile renderer owns the final image startup semantics for these families. Treating an auto-detected runtime command as a user ENTRYPOINT would change the meaning of the generated image.

## DockerfileGenerator

**Path:** \`core/dockerfile.py\`

### Called by

DeploymentOrchestrator after configuration/platform information is resolved.

### Input

DeploymentConfig-derived build/platform/runtime settings.

### Output

Dockerfile/build instructions used by the application image build.

### It may express

- runtime base;
- dependency installation;
- frontend build stages;
- document/static/media paths;
- process entrypoint/start command;
- healthcheck instructions.

### It must not decide

- tenant security policy;
- worker ownership;
- lifecycle state;
- arbitrary runtime backend selection.

## Runtime version

Runtime version can arrive from explicit config or platform detection, but the final base-image identity is operator-owned through BaseImageSpec.

This prevents “runtime version string” from becoming arbitrary Docker-image selection.

## Frontend builds

Laravel/full-stack PHP projects may also require Node tooling.

The build pipeline can detect/receive frontend settings such as:

- package manager;
- build/install command;
- frontend kind;
- npm registry.

The important distinction is:

~~~text
frontend build tooling
      !=
runtime backend
~~~

A Node build stage can be part of an application image without changing the application's runtime family from PHP.

## Document root

PHP/Laravel document root is an application configuration concern.

The base PHP runtime is generic; application-specific document root is applied later by Dockerfile generation.

### Architectural reason

Putting application document-root semantics into the shared PHP base image would fragment the reusable base identity and force base-image rebuilds for tenant-level path differences.

## Base image versus application image

~~~text
operator-owned runtime/tooling layers
        +
application source + dependency/build instructions
        =
deployment-specific application image
~~~

Shared base images must never absorb tenant source or tenant dependency trees.

## Build resource ownership

\`common/resource_policy.py\` determines build resource limits from operator-owned configuration, optionally constrained by operator plan build mode.

Tenant JSON is not the authority for CPU/RAM/PIDs/shm.

### Why

Build containers share the host with other deployments and therefore require server-side isolation and accounting.

## Application image lifecycle

The image manager receives the generated build context and Dockerfile.

A successful build yields the image reference used by runtime.

### Postcondition

Image existence is necessary but not sufficient for deployment success. Runtime apply and readiness still have to succeed.

## Failure navigation

| Symptom | Start | Reason |
|---|---|---|
| wrong detected framework | PlatformRegistry + plugin | evidence/priority problem |
| correct detection, wrong command | ProjectConfig sources + platform bridge | enrichment/precedence problem |
| correct config, wrong Dockerfile | DockerfileGenerator | rendering problem |
| correct Dockerfile, build fails | image manager + build diagnostics | Docker/build problem |
| image builds, container fails | runtime/health docs | runtime problem |

## What this layer must NOT do

- platform plugins must not call Docker;
- detection must not mutate deployment state;
- Dockerfile generation must not choose host infrastructure;
- application image build must not rebuild shared base policy;
- a frontend build must not silently change runtime backend policy.

## Related code

- \`src/deployments/core/platforms/inspector.py\`
- \`src/deployments/core/platforms/registry.py\`
- \`src/deployments/core/platforms/base/platform.py\`
- \`src/deployments/core/platforms/base/schema.py\`
- \`src/deployments/core/platforms/loader.py\`
- \`src/deployments/core/platform_bridge.py\`
- \`src/deployments/core/dockerfile.py\`
- \`src/deployments/core/manager/image_manager.py\`
- \`src/deployments/common/resource_policy.py\`
