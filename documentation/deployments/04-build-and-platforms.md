# 04 — Build and platforms

## Purpose

Document how PassDeployer turns an uploaded project into an application image without mixing source inspection, policy, Docker execution and runtime lifecycle.

## Platform pipeline

~~~text
uploaded ZIP
  -> ProjectInspector
  -> PlatformRegistry
  -> DetectionResult
  -> platform-specific ProjectConfig
  -> deployment config enrichment
  -> DockerfileGenerator
  -> application image
~~~

## Project inspection

deployments.core.platforms.inspector.ProjectInspector walks a bounded project tree and creates:

- file_index: relative path -> absolute path;
- dir_index: known directories;
- markers: known platform/build marker files.

It deliberately skips source-control, dependency/cache and generated-output directories such as .git, node_modules, virtual environments, vendor and build/dist trees.

The inspector does not build or mutate Docker resources.

## Platform registry

PlatformRegistry.detect():

1. creates a ProjectInspector;
2. runs every registered platform plugin's detect();
3. collects candidate confidence scores;
4. honors an explicit preferred platform when one matches;
5. otherwise selects highest confidence, then plugin priority;
6. resolves the selected plugin into ProjectConfig.

A generic platform is the final fallback when registered.

## Supported platform/plugin families

The current loader registers:

### Node

NodePlatform, ReactPlatform, NextPlatform, VitePlatform, VuePlatform, AngularPlatform, ExpressPlatform.

### Python

PythonPlatform, DjangoPlatform, FlaskPlatform, FastAPIPlatform.

### PHP

PHPPlatform, LaravelPlatform.

### Other

GoPlatform, StaticPlatform, GenericPlatform.

These are actual registered classes in core/platforms/loader.py. Do not document a framework as supported merely because a config key exists; verify the plugin registry.

## Plugin contract

BasePlatform defines:

- detect(file_index): identify whether the project matches;
- defaults(): platform defaults;
- inspect(file_index): concrete values inferred from the source tree;
- validate(config): framework/platform validation;
- resolve(): merge defaults, detection and user config into ProjectConfig.

The plugin may own framework-specific interpretation of source files.

It must not:

- call the Docker daemon;
- mutate Deploy/Service lifecycle state;
- choose host runtime infrastructure;
- bypass the build resource policy;
- silently broaden tenant permissions.

## Platform merge order

The concrete plugin resolver uses:

~~~text
platform defaults < auto-detected values < user config
~~~

The newer planning resolver separately enforces operator policy ceilings. These are related boundaries, not duplicate sources of host policy.

## Framework refinement

The current application path allows the service plan to establish the execution family while configuration/detection refines a framework inside that family.

Examples include PHP + Laravel and Python + Django.

Framework identity can change Dockerfile generation and runtime paths without letting the tenant select arbitrary infrastructure.

## Dockerfile generation

deployments.core.dockerfile.DockerfileGenerator consumes the resolved platform/configuration.

The generated image may include runtime base, application dependencies, frontend build stages where required, static/document/media paths, process entrypoint/start command and runtime healthcheck data.

For PHP/Laravel, frontend settings can add a Node/Vite/React-style build step while keeping the base runtime image operator-owned.

For Django/Python, entrypoint discovery may inspect settings/module structure before generation.

## Base image versus application image

~~~text
operator-owned base image
    + source/build instructions
    = application image
~~~

A base runtime image contains runtime/tooling layers only. Tenant application source and tenant dependencies do not become part of the shared base registry artifact.

See 08-base-images.md for base-image lifecycle.

## Build options

Public build options are intentionally narrow. normalize_profile() maps compatibility aliases, but tenant build options ultimately honor an allow-list such as target, no-cache and pull where supported.

Build resource limits are derived from operator settings, not tenant JSON.

## Application image identity

The application image is produced by the image manager after Dockerfile generation and source tar preparation.

The current orchestrator passes the deployment correlation id to the image builder for diagnostics and ownership-aware cancellation.

A successful image build produces the image reference later consumed by the runtime.

## What belongs where

**Platform plugin:** what kind of project is this and what defaults does that imply?

**Planning:** which normalized, policy-compliant values should execution use?

**Dockerfile generator:** how do those values become image build instructions?

**Image manager:** how does Docker build the application image?

**Runtime:** how do we run that image?

Do not move runtime Docker calls into platform plugins because a plugin already knows the framework.

## Failure behavior

- no detector -> generic fallback or hard failure if none registered;
- invalid detected/user configuration -> validation/security error;
- unsafe command/path -> validation/security error;
- Docker build failure -> application image build error;
- internal programming error -> non-recoverable platform error at the worker boundary.

## Related code

- src/deployments/core/platforms/inspector.py
- src/deployments/core/platforms/registry.py
- src/deployments/core/platforms/base/platform.py
- src/deployments/core/platforms/loader.py
- src/deployments/core/platform_bridge.py
- src/deployments/core/dockerfile.py
- src/deployments/core/manager/image_manager.py
- src/deployments/common/resource_policy.py
- src/deployments/common/security.py
