# 08 — Base images

## Purpose

Base runtime images have a separate operator-owned lifecycle. Application deployments consume them; they do not own ordinary renewal policy.

This distinction is essential when diagnosing “Base image resolution…” messages or unexpected base-image waiting/building.

## Base image definition

BaseImageSpec contains:

- logical_runtime;
- version;
- variant;
- source_image;
- repository;
- tag;
- Dockerfile definition.

Its definition fingerprint is a SHA-256 digest over the operator-owned definition inputs.

Built images carry:

- io.passdeployer.base-definition;
- io.passdeployer.base-runtime.

These labels let the resolver verify that a local artifact matches the current definition.

## Current runtime families

deploy/base_images.py::make_specs() currently defines:

- PHP/Laravel-family -> paas-base/php-apache, variant apache;
- Python-family -> paas-base/python-slim;
- Node-family -> paas-base/node-alpine;
- static/frontend families may also require paas-base/nginx;
- static -> paas-base/nginx;
- Go -> paas-base/go-alpine.

Legacy PHP variants apache-root and apache-public can still be reconstructed for old in-flight rows. They are compatibility data; the canonical PHP identity is the apache variant.

## Registry state

BaseRuntimeImage states are:

~~~text
PENDING
BUILDING
READY
FAILED
DISABLED
~~~

The model also tracks:

- source/image reference;
- image id/digest;
- build start/completion;
- build count;
- build task id;
- build owner deployment id;
- definition fingerprint;
- rebuild_requested;
- last error and structured details.

Identity includes logical runtime, version, variant, architecture and docker_host.

BaseRuntimeImageLease records which deployments currently rely on the shared artifact.

## Resolution algorithm

For every required BaseImageSpec, ensure_base_images():

1. computes the expected definition fingerprint;
2. finds or creates the host-specific BaseRuntimeImage row;
3. detects definition/reference changes;
4. inspects the local Docker image;
5. accepts a compatible local image when policy permits;
6. may use a last-known-good local artifact while a renewal row is pending/building/failed;
7. if no usable artifact exists, acquires BUILDING ownership;
8. queues build_base_runtime_image on base-images;
9. waits for READY or failure/timeout;
10. returns the image reference and acquires a deployment lease.

## The cache rule

Registry status alone does not decide usability.

A compatible local image is reusable when:

- the image exists locally;
- its io.passdeployer.base-definition label matches the expected fingerprint.

Such an image can be used even while the row is BUILDING because a background renewal may be in progress.

There is also a last-known-good path for certain PENDING/BUILDING/FAILED rows. It prefers the recorded image id, then the expected runtime label, then an explicit exact-reference fallback for older operator-owned images.

Therefore:

~~~text
application deployment
    !=
base-image renewal
~~~

## When an application deployment can trigger a build

A deployment queues a base-image build only when no acceptable local artifact is available and the row is not already owned by another build.

A definition fingerprint change can request a renewal.

This is a prerequisite relationship, not ownership transfer: the application deployment needs a base artifact but does not become the policy owner of its definition.

## Concurrent builds

When a row is already BUILDING:

- a second worker does not create a duplicate build for the same base identity;
- an exact compatible local artifact may bypass the wait;
- otherwise the deployment waits for the shared build result;
- the wait is bounded by the deployment's base-image phase deadline.

If the worker that owns the build disappears and no reusable local image exists, stale BUILDING state can be recovered after the operator timeout.

## Dedicated base-image worker

build_base_runtime_image is routed to base-images.

Compose runs base-image-worker with concurrency 1 by default.

Deployment workers do not consume that queue. This prevents synchronous waiter deadlocks at low deployment-worker concurrency.

## Build ownership

The registry row stores:

- build_task_id;
- build_owner_deployment_id;
- build_started_at.

The builder uses ownership checks while building/streaming.

The monitor can mark an expired BUILDING row FAILED so waiters are released and a later build can safely claim it.

## Application/base phase clocks

A Deploy has separate time fields:

~~~text
base_image_wait_started_at
        |
        v
base_image_ready_at
        |
        v
application_started_at
~~~

mark_base_image_phase_started() starts the base-image budget.

mark_application_phase_started() records base readiness and starts a fresh application budget.

A slow shared base-image build therefore does not consume the entire application deployment timeout.

## Operator rebuild path

request_base_runtime_image_build() is the manual/operator request path.

It changes registry/build state and queues build_base_runtime_image. It does not perform a synchronous Docker build from HTTP.

## Cleanup and leases

The orchestrator releases deployment base-image leases in its finally path.

release_stale_base_image_leases() can release old leases when the owning Deploy is already terminal.

If operator policy does not retain base images after deployment, lease-aware cleanup may remove an image only when no active deployment still references it.

## Failure semantics

When a required base image cannot become ready:

- application Dockerfile/image build does not start;
- the deployment receives a base-image failure or timeout;
- structured Docker/build diagnostics remain on the base-image row;
- retry classification belongs to the dedicated base-image task.

A failed renewal does not justify falling back to an incompatible image.

## Debugging checklist

When logs show “Base image resolution…” inspect:

1. BaseRuntimeImage.status;
2. image_ref;
3. definition_fingerprint;
4. local Docker image existence;
5. io.passdeployer.base-definition label;
6. rebuild_requested;
7. build_task_id;
8. build_owner_deployment_id;
9. last_error_details.

This separates cache/registry state from application image-build behavior.

## What this subsystem must NOT do

Base image code must not:

- copy tenant application source or dependency trees into shared base images;
- silently rebuild a compatible local base merely because a renewal flag exists;
- allow tenant resource settings to become the base-image build resource policy;
- remove a base artifact still protected by an active deployment lease;
- treat the application Dockerfile as the base-image definition.

## Related code

- src/deploy/base_images.py
- src/deploy/models.py
- src/deployments/celery/tasks.py
- src/deployments/celery/schedules.py
- src/deployments/core/orchestrator.py
- src/deployments/common/resource_policy.py
