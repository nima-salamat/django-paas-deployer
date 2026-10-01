# PassDeployer Agent

## Identity

- Agent ID: {{ agent_id }}
- API version: v1
- API base URL: {{ api_base_url }}

This file is generated for this specific Agent. It is not a static repository credential file.

## Authentication and enrollment

A short-lived, single-use bootstrap credential is supplied below:

    PASSDEPLOYER_ENROLLMENT_TOKEN="{{ enrollment_token }}"

Exchange it exactly once:

    POST {{ api_base_url }}/auth/exchange

    {"enrollment_token":"$PASSDEPLOYER_ENROLLMENT_TOKEN"}

The exchange invalidates the enrollment credential and returns a normal Bearer access token. Store the permanent access token only in a secure external secret store. Never put a permanent token in a URL, repository, source file, or log.

## Capabilities

Only capabilities issued to this Agent are listed:

{% for scope in scopes %}
- {{ scope }}
{% empty %}
- No operational scopes are enabled.
{% endfor %}

Discover machine-readable capabilities:

    GET {{ api_base_url }}/capabilities

OpenAPI:

    GET {{ api_base_url }}/openapi.json

## Resources

### Services

    GET {{ api_base_url }}/services
    POST {{ api_base_url }}/services
    GET {{ api_base_url }}/services/{service_id}
    PATCH {{ api_base_url }}/services/{service_id}
    DELETE {{ api_base_url }}/services/{service_id}

Lifecycle:

    POST {{ api_base_url }}/services/{service_id}/start
    POST {{ api_base_url }}/services/{service_id}/stop
    POST {{ api_base_url }}/services/{service_id}/restart
    POST {{ api_base_url }}/services/{service_id}/purge-runtime

Status and runtime logs:

    GET {{ api_base_url }}/services/{service_id}/status
    GET {{ api_base_url }}/services/{service_id}/logs

### Plans

    GET {{ api_base_url }}/plans
    GET {{ api_base_url }}/plans/{plan_id}
    POST {{ api_base_url }}/plans/{plan_id}/apply

Create from plan:

    POST {{ api_base_url }}/services/from-plan

Service creation requires a valid user-owned Private Network. Inspect networks first or create a network only when the Agent has the corresponding scope.

### Networks and volumes

    GET/POST {{ api_base_url }}/networks
    GET/PATCH/DELETE {{ api_base_url }}/networks/{network_id}

    GET/POST {{ api_base_url }}/volumes
    GET/PATCH/DELETE {{ api_base_url }}/volumes/{volume_id}

### Deployments

    GET {{ api_base_url }}/deployments
    POST {{ api_base_url }}/deployments
    GET {{ api_base_url }}/deployments/{deployment_id}
    POST {{ api_base_url }}/deployments/{deployment_id}/upload
    POST {{ api_base_url }}/deployments/{deployment_id}/start
    POST {{ api_base_url }}/deployments/{deployment_id}/cancel
    POST {{ api_base_url }}/deployments/{deployment_id}/redeploy
    POST {{ api_base_url }}/deployments/{deployment_id}/rebuild
    POST {{ api_base_url }}/deployments/{deployment_id}/rollback

### Deployment logs

    GET {{ api_base_url }}/deployments/{deployment_id}/logs

### Runtime service logs

    GET {{ api_base_url }}/services/{service_id}/logs
    GET {{ api_base_url }}/services/{service_id}/logs/export

### Configuration

Configuration, environment, secrets, endpoints, networks and database bindings are exposed only when their corresponding scopes and the existing user/service permissions allow them.

    GET/PATCH {{ api_base_url }}/services/{service_id}/configuration
    GET/POST/DELETE {{ api_base_url }}/services/{service_id}/environment
    GET/POST/DELETE {{ api_base_url }}/services/{service_id}/secrets
    GET/POST/DELETE {{ api_base_url }}/services/{service_id}/endpoints
    GET/POST/DELETE {{ api_base_url }}/services/{service_id}/networks
    GET/POST/DELETE {{ api_base_url }}/services/{service_id}/databases

### Revisions

    GET {{ api_base_url }}/services/{service_id}/revisions
    GET {{ api_base_url }}/services/{service_id}/revisions/{revision_id}
    POST {{ api_base_url }}/services/{service_id}/revisions/{revision_id}/rollback

### Restricted shell

    GET {{ api_base_url }}/services/{service_id}/shell
    POST {{ api_base_url }}/services/{service_id}/shell/sessions
    POST {{ api_base_url }}/services/{service_id}/shell/sessions/{session_id}/commands
    POST {{ api_base_url }}/services/{service_id}/shell/sessions/{session_id}/close
    POST {{ api_base_url }}/services/{service_id}/shell/replace

## Common workflows

### Inspect services

    GET {{ api_base_url }}/services

### Create service from plan

1. Inspect the plan.
2. Inspect the user's Private Networks.
3. Supply an existing network or create one when permitted.
4. Call:

    POST {{ api_base_url }}/services/from-plan

### Deploy ZIP/source archive

1. Create deployment metadata.
2. Upload the ZIP.
3. Start the deployment.
4. Poll deployment status.
5. Read deployment logs.

    POST {{ api_base_url }}/deployments
    POST {{ api_base_url }}/deployments/{id}/upload
    POST {{ api_base_url }}/deployments/{id}/start
    GET  {{ api_base_url }}/deployments/{id}/logs

The audited production path currently supports ZIP/archive application deployment and database-native deployment. Git and existing-image inputs are not advertised as first-class Agent deployment sources.

### Diagnose a failed deployment

Deployment logs and runtime service logs are intentionally separate.

Deployment logs answer:

- Why did build/orchestration/lifecycle fail?
- Which deployment stage failed?
- Why was deployment cancelled?

Use:

    GET {{ api_base_url }}/deployments/{id}/logs

Runtime service logs answer:

- Why is Django returning HTTP 500?
- Why is Laravel raising an exception?
- Why is Node crashing?
- What is the application printing?

Use:

    GET {{ api_base_url }}/services/{id}/logs

Never merge these sources into one ambiguous stream.

### Execute a command inside a service

1. Check shell capability.
2. Create or reuse an authorized restricted shell session.
3. Execute through the existing shell policy.
4. If the policy returns CONFIRMATION_REQUIRED, obtain explicit user authorization before retrying with confirm=true.
5. Return exit code, bounded stdout/stderr, duration and cwd.

Shell execution always occurs inside the service runtime/container. There is no host shell or raw Docker API.

## Important rules

- Deployment IDs, release IDs, service IDs and revision IDs are distinct.
- Revisions are immutable; rollback uses the existing rollback boundary rather than mutating an old revision.
- Agent scopes are an upper bound. Existing PassDeployer User authorization and ServiceShare action permissions also apply.
- Normal service secret reads are metadata-only and masked. Never attempt to recover plaintext secret values from logs, configuration, or errors.
- Destructive shell operations retain the existing forbidden-binary and shell-operator restrictions, path/workdir confinement, session TTL, output limits and confirmation behavior.
- The Agent API never exposes host command execution, Docker socket access or raw Docker APIs.
- Send Idempotency-Key on retries of logical mutating operations. Keys are scoped to the Agent, method, path and request shape and retained for 24 hours.
- Unsupported capabilities must not be assumed. Re-check GET {{ api_base_url }}/capabilities before using an operation.

## Error handling

Structured errors may include:

    code
    detail
    request_id
    retryable
    failure_domain
    visibility
    resource_effect
    certainty

Distinguish invalid input, authentication failure, insufficient scope, ServiceShare denial, resource not found, transient infrastructure failure, cancellation, confirmation required, and unsupported capability before retrying.
