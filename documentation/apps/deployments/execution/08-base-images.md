# 08 — Base runtime images

## Purpose

A BaseRuntimeImage is **operator-owned reusable runtime infrastructure**.

An application image is **a deployment-specific artifact built from application source**.

They are different lifecycles with different ownership, queues, cache rules and failure semantics.

```text
BaseRuntimeImage
  operator definition + runtime/tooling
          |
          +----------------+
                           |
Application source + build |
                           v
                 Application image
                           |
                           v
                        Runtime
```

## Why base images have their own lifecycle

Shared runtime layers are expensive to build and useful across deployments.

Treating a base image like an ordinary application artifact would:

- duplicate builds across services;
- mix tenant source with operator runtime policy;
- make runtime-version changes harder to reason about;
- make application deployment timeouts depend on unrelated renewal work.

The registry therefore tracks shared base state independently.

## BaseImageSpec

**Path:** `deploy/base_images.py`

Contains:

- logical_runtime;
- version;
- variant;
- source_image;
- repository;
- tag;
- Dockerfile.

The definition fingerprint is a SHA-256 digest of these operator-owned definition inputs.

Built images carry the fingerprint as `io.passdeployer.base-definition`.

## Registry model

**Path:** `deploy/models.py::BaseRuntimeImage`

Identity is host-scoped:

```text
logical_runtime
+ runtime_version
+ variant
+ architecture
+ docker_host
```

State:

| State | Meaning | Who may cause it |
|---|---|---|
| PENDING | definition exists but no usable build is currently committed | resolver/operator |
| BUILDING | a build owner is active | base-image worker |
| READY | registry points at a usable artifact | successful builder/local adoption |
| FAILED | last build attempt failed/expired | builder/monitor |
| DISABLED | operator disabled the base | operator |

A failed state does not automatically mean no usable local artifact exists.

## Definition compatibility

A local image is “exactly compatible” when:

1. image reference exists locally;
2. its `io.passdeployer.base-definition` label matches the expected fingerprint.

This protects against reusing an old Docker image under the same human-readable tag after the operator changes the base Dockerfile.

## Last-known-good behavior

During a PENDING/BUILDING/FAILED renewal, the registry may retain:

- image_id;
- image_digest;
- exact reference;
- runtime label.

A deployment may use this artifact where the compatibility helper explicitly permits it.

### Why failed renewal preserves old artifact

Suppose:

```text
READY old image
       |
operator starts renewal
       |
BUILDING
       |
build fails
```

If the old artifact were discarded at the start, every application deployment would become unavailable because of an unrelated base renewal failure.

Keeping the last usable artifact decouples application availability from renewal success.

## Resolution algorithm

**Path:** `ensure_base_images()`

For each required spec:

1. compute definition fingerprint;
2. find/create host-specific registry row;
3. update changed source/reference metadata;
4. inspect the local Docker artifact;
5. prefer exact compatible local reuse;
6. consider permitted last-known-good reuse;
7. if no reusable artifact exists, claim BUILDING;
8. queue dedicated build task;
9. wait for READY/failure/timeout;
10. return image reference;
11. acquire a deployment lease while using it.

## Application deployment versus renewal

```text
application deployment
    asks: “Can I obtain a usable base artifact?”

base-image renewal
    asks: “Should the operator-defined shared artifact be rebuilt?”
```

The first may depend on the second, but they are not the same operation.

### BUILDING + compatible local image

Continue deployment.

The background renewal can continue.

### BUILDING + incompatible/missing local image

Wait for the shared build.

Do not start a second build for the same identity.

### FAILED + compatible/last-known-good local image

Deployment may continue through the explicitly permitted fallback.

### FAILED + no usable local image

Deployment fails with a base-image error.

## Build ownership

The row stores:

- build_task_id;
- build_owner_deployment_id;
- build_started_at;
- build_completed_at;
- last_error/last_error_details.

The task updates are matched against the current task id.

### Why task-id matching matters

Without fencing:

```text
old worker times out
new worker starts
old worker reports failure
       -> new build incorrectly becomes FAILED
```

Task-id matching prevents this.

## Queue ownership

`build_base_runtime_image` is routed to `base-images`.

Compose's base-image worker consumes only this queue and defaults to concurrency 1.

### Why a dedicated queue

Application deployments may synchronously wait for a base build. If the same low-concurrency worker pool consumed the child build task, the parent could wait forever for work it is preventing from running.

## Base-image phase clock

Deploy has:

- `base_image_wait_started_at`;
- `base_image_ready_at`;
- `application_started_at`.

The intended timeline is:

```text
base-image wait budget
       |
       v
base image ready
       |
       v
fresh application deployment budget
```

A base wait must not silently consume the complete application timeout.

## Operator rebuild path

`request_base_runtime_image_build()` is the explicit operator/manual request path.

It:

1. locks the BaseRuntimeImage row;
2. records the requested lifecycle change;
3. queues `build_base_runtime_image`;
4. preserves ownership of the currently active artifact.

It does not run a Docker build synchronously from an HTTP handler.

## Lease semantics

`BaseRuntimeImageLease` protects a shared base artifact from cleanup while a deployment is using it.

The application deployment acquires a lease before/while consuming the image and releases it in the lifecycle cleanup path.

Stale leases can be released after their owning Deploy is terminal.

## Timeout/recovery

The monitor can detect a BUILDING row older than the operator base-image build timeout.

It marks it FAILED and clears build ownership.

A subsequent deployment can then either:

- use a local last-known-good artifact;
- or claim a fresh build.

## Failure semantics

If no usable base artifact exists:

- application Dockerfile/image build does not begin;
- the deployment remains in the base-image phase;
- diagnostics remain on BaseRuntimeImage/Deploy;
- retry behavior follows the base-image task's own classification.

A failed renewal must not force incompatible fallback.

## Debugging a base-image rebuild/wait

Read in this order:

1. `BaseRuntimeImage.status`
2. `image_ref`
3. `definition_fingerprint`
4. local image existence
5. local `io.passdeployer.base-definition`
6. `rebuild_requested`
7. `build_task_id`
8. `build_owner_deployment_id`
9. `last_error_details`

Then inspect application Deploy timing to see whether the base phase or application phase timed out.

## What this subsystem must NOT do

Do not:

- put tenant source/dependencies into the shared base;
- rebuild an exact-compatible local artifact just because a renewal row is BUILDING;
- use tenant resource limits for base-image builds;
- release a base artifact while an active lease exists;
- mutate application deployment state as if a renewal were an application deploy.

## Related code

- `src/deploy/base_images.py`
- `src/deploy/models.py`
- `src/deployments/celery/tasks.py`
- `src/deployments/celery/schedules.py`
- `src/deployments/common/resource_policy.py`
- `src/deployments/core/orchestrator.py`
