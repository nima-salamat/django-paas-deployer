# PassDeployer Architecture

PassDeployer is a single-host Docker PaaS control plane. The application database stores desired state; deployments execute immutable revisions; Docker is the runtime substrate.

## Core ownership

Service owns source, build/runtime configuration, environment, secrets, processes, endpoints, networks, volumes and database bindings.
ServiceRevision is an immutable executable snapshot and owns the deployable source artifact.
Deploy is an execution operation linked to a revision and keeps historical/provenance state.
Service.desired_state is the declarative lifecycle target; Runtime is observed Docker state and is never the configuration source of truth.

## Execution flow

input representation -> normalize/validate -> Service domain -> ServiceRevision -> normalized runtime graph -> Docker/Traefik execution

Supported inputs include archive/Git, Dockerfile, existing image, Compose and catalog definitions.
Compose is an input format. It is parsed and normalized; the PaaS does not make Docker Compose the runtime engine.

## Domain objects

### Service
User-owned deployable workload and lifecycle state.

### ServiceProcess
Web, worker, scheduler or custom executable process. Non-web processes are executed as independent, revision-labelled Docker containers; replicas are bounded by server policy.

### ServiceRevision
Immutable snapshot containing source/build/runtime metadata, processes, endpoints, volumes, networks, environment metadata and versioned secret references.

### Deploy
Compatibility/API operation record. New executable changes create a new Deploy and a new Revision.

### Runtime graph
deployments.core.runtime_graph.ServiceRuntimeGraph converts a revision into Docker-neutral runtime semantics.

## Secrets
Secrets are versioned and encrypted at rest. Revisions contain exact secret references, never plaintext. Service configuration JSON rejects sensitive keys and requires the secret API.

## Networking
ServiceEndpoint separates target port from published host port and public/internal exposure. TCP/UDP published ports are protected by ServicePortReservation.

## Databases
DatabaseResource represents a managed/external database resource. ServiceDatabaseBinding connects a workload Service to that resource. Database deployment also executes through a ServiceRevision.

## Rollback
Rollback creates a new deployment operation targeting an existing immutable revision. It does not rewrite historical Deploy configuration.

## Transitional states
Configuration changes are blocked while queued, deploying or stopping. Changes are allowed while stopped or running and become effective on the next deployment.

## App catalog
app_catalog owns templates, variants, Compose normalization and multi-service dependency coordination. Child Services still use the normal deployment engine.

## Documentation convention
Every Django app and major internal subsystem keeps a README describing responsibility, boundaries, models and API endpoints.
