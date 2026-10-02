# Agent API

The `agent` app exposes a stable versioned control-plane API at `/agent/v1/`.

## Architecture

Agent authentication, scopes, API contracts, rate limiting, idempotency and audit live in the Agent application. Endpoint authorization metadata is defined once in `agent.contracts` and projected into runtime checks, capabilities, OpenAPI and `AGENT.md`. Resource operations delegate to the existing PassDeployer application/service boundaries.

The Agent app does not become a Docker runtime owner, deployment orchestrator, second share/permission model, second log database, or second shell security system.

The current production deployment path remains the audited `Celery task -> DeployService -> DeployFacade -> DeploymentOrchestrator` path. The newer `DeploymentLifecycleExecutor -> RuntimeContract -> RuntimeAdapter` architecture remains an underlying migration concern.

## Authentication

Browser authentication remains `SessionJWTAuthentication`. Agent access uses separate Bearer credentials.

Persistent Agent access credentials are stored as HMAC-SHA256 digests, expire and can be revoked independently. Enrollment credentials use deterministic SHA-256 digests because they are cryptographically random, short-lived, and single-use; this keeps bootstrap exchange stable across application processes even if runtime secret configuration differs. Enrollment credentials become invalid after one exchange.

## Authorization

Agent authorization is an intersection:

`Agent scope` AND `existing PassDeployer User authorization` AND, for shared services, `ServiceShare action permission`.

A superuser flag never creates missing Agent scopes.

## API

The resource-oriented API covers services, plans, networks, volumes, deployments, immutable revisions, deployment logs, runtime service logs and restricted service-container shell sessions.

Machine-readable discovery is available from:

- `GET /agent/v1/capabilities`
- `GET /agent/v1/openapi.json`
- `GET /agent/v1/agent.md`

## Enrollment

The generated `AGENT.md` contains a short-lived, single-use bootstrap credential intentionally issued for that specific Agent.

The Agent is expected to use this credential to authenticate. Sensitivity does not mean the credential is unusable: the correct behavior is to use it internally and never disclose, echo, log, publish, or place it in URLs or source files.

Exchanging the enrollment credential returns a normal Bearer access credential. Permanent credentials are never embedded in repository templates or URLs.

## Logs

Deployment lifecycle logs are `DeployLog` records and are queried through the existing deployment-log mechanism. Runtime application logs are `ServiceLogStream`/`ServiceLogEntry` records queried through `logs.query`. The Agent API keeps the two sources separate.

## Shell

Shell access delegates to the existing restricted shell subsystem. Commands are executed inside the authorized service runtime and retain existing forbidden-command/operator checks, path/workdir confinement, TTL, output limits, confirmation requirements and share permissions.

## Deployment inputs

Only verified inputs are advertised: ZIP/archive application deployments and database-native deployment. Git and existing-image deployment are intentionally not advertised as first-class Agent deployment inputs in this version.

## Security and operations

Important mutating operations support durable `Idempotency-Key` semantics. Agent-specific throttles are stricter for deployment, upload and shell actions. Audit records are sanitized and do not contain bearer/enrollment/shell credentials or plaintext service secrets.
