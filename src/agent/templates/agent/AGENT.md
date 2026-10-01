# PassDeployer Agent

## Identity

- Agent ID: {{ agent_id }}
- API version: v1
- API base URL: {{ api_base_url }}

This file is generated for this specific Agent. Its endpoint list is restricted to capabilities issued to this Agent.

## Authentication and enrollment

PASSDEPLOYER_ENROLLMENT_TOKEN="{{ enrollment_token }}"

Exchange it exactly once:

    POST {{ api_base_url }}/auth/exchange
    {"enrollment_token":"$PASSDEPLOYER_ENROLLMENT_TOKEN"}

The exchange invalidates the enrollment credential and returns a normal Bearer access token. Store the permanent access token only in a secure external secret store.
Never put a permanent token in a URL, repository, source file, or log.

## Capabilities

{% for scope in scopes %}- `{{ scope }}`
{% empty %}- No operational scopes are enabled.
{% endfor %}

Discover the machine-readable capability document:

    GET {{ api_base_url }}/capabilities

OpenAPI:

    GET {{ api_base_url }}/openapi.json

{% if capabilities.services.read or capabilities.services.create or capabilities.services.update or capabilities.services.delete or capabilities.services.start or capabilities.services.stop or capabilities.services.restart or capabilities.services.purge %}
## Services
{% if capabilities.services.read %}    GET {{ api_base_url }}/services
    GET {{ api_base_url }}/services/{service_id}
    GET {{ api_base_url }}/services/{service_id}/status{% endif %}
{% if capabilities.services.create %}    POST {{ api_base_url }}/services
    POST {{ api_base_url }}/services/from-plan{% endif %}
{% if capabilities.services.update %}    PATCH {{ api_base_url }}/services/{service_id}{% endif %}
{% if capabilities.services.delete %}    DELETE {{ api_base_url }}/services/{service_id}{% endif %}
{% if capabilities.services.start %}    POST {{ api_base_url }}/services/{service_id}/start{% endif %}
{% if capabilities.services.stop %}    POST {{ api_base_url }}/services/{service_id}/stop{% endif %}
{% if capabilities.services.restart %}    POST {{ api_base_url }}/services/{service_id}/restart{% endif %}
{% if capabilities.services.purge %}    POST {{ api_base_url }}/services/{service_id}/purge-runtime{% endif %}
{% endif %}

{% if capabilities.plans.read or capabilities.plans.apply or capabilities.plans.manage %}
## Plans
{% if capabilities.plans.read %}    GET {{ api_base_url }}/plans
    GET {{ api_base_url }}/plans/{plan_id}{% endif %}
{% if capabilities.plans.apply %}    POST {{ api_base_url }}/plans/{plan_id}/apply{% endif %}
{% if capabilities.plans.manage %}    POST {{ api_base_url }}/plans/manage
    PATCH {{ api_base_url }}/plans/manage/{plan_id}
    DELETE {{ api_base_url }}/plans/manage/{plan_id}{% endif %}
{% endif %}

{% if capabilities.networks.read or capabilities.networks.write %}
## Networks
{% if capabilities.networks.read %}    GET {{ api_base_url }}/networks
    GET {{ api_base_url }}/networks/{network_id}{% endif %}
{% if capabilities.networks.write %}    POST {{ api_base_url }}/networks
    PATCH {{ api_base_url }}/networks/{network_id}
    DELETE {{ api_base_url }}/networks/{network_id}{% endif %}
{% endif %}

{% if capabilities.volumes.read or capabilities.volumes.write %}
## Volumes
{% if capabilities.volumes.read %}    GET {{ api_base_url }}/volumes
    GET {{ api_base_url }}/volumes/{volume_id}{% endif %}
{% if capabilities.volumes.write %}    POST {{ api_base_url }}/volumes
    PATCH {{ api_base_url }}/volumes/{volume_id}
    DELETE {{ api_base_url }}/volumes/{volume_id}{% endif %}
{% endif %}

{% if capabilities.deployments.read or capabilities.deployments.create or capabilities.deployments.upload or capabilities.deployments.start or capabilities.deployments.cancel or capabilities.deployments.redeploy or capabilities.deployments.rebuild or capabilities.deployments.rollback or capabilities.deployments.delete or capabilities.deployments.logs_read or capabilities.deployments.logs_export %}
## Deployments
{% if capabilities.deployments.read %}    GET {{ api_base_url }}/deployments
    GET {{ api_base_url }}/deployments/{deployment_id}{% endif %}
{% if capabilities.deployments.create %}    POST {{ api_base_url }}/deployments{% endif %}
{% if capabilities.deployments.upload %}    POST {{ api_base_url }}/deployments/{deployment_id}/upload{% endif %}
{% if capabilities.deployments.start %}    POST {{ api_base_url }}/deployments/{deployment_id}/start{% endif %}
{% if capabilities.deployments.cancel %}    POST {{ api_base_url }}/deployments/{deployment_id}/cancel{% endif %}
{% if capabilities.deployments.redeploy %}    POST {{ api_base_url }}/deployments/{deployment_id}/redeploy{% endif %}
{% if capabilities.deployments.rebuild %}    POST {{ api_base_url }}/deployments/{deployment_id}/rebuild{% endif %}
{% if capabilities.deployments.rollback %}    POST {{ api_base_url }}/deployments/{deployment_id}/rollback{% endif %}
{% if capabilities.deployments.delete %}    DELETE {{ api_base_url }}/deployments/{deployment_id}{% endif %}
{% if capabilities.deployments.logs_read %}    GET {{ api_base_url }}/deployments/{deployment_id}/logs{% endif %}
{% if capabilities.deployments.logs_export %}    GET {{ api_base_url }}/deployments/{deployment_id}/logs/export{% endif %}
{% endif %}

{% if capabilities.runtime_logs.read or capabilities.runtime_logs.export %}
## Runtime service logs
{% if capabilities.runtime_logs.read %}    GET {{ api_base_url }}/services/{service_id}/logs{% endif %}
{% if capabilities.runtime_logs.export %}    GET {{ api_base_url }}/services/{service_id}/logs/export{% endif %}
{% endif %}

{% if capabilities.config.read or capabilities.config.write or capabilities.environment.read or capabilities.environment.write or capabilities.secrets.read or capabilities.secrets.write or capabilities.endpoints.read or capabilities.endpoints.write or capabilities.service_networks.read or capabilities.service_networks.write %}
## Service configuration
{% if capabilities.config.read %}    GET {{ api_base_url }}/services/{service_id}/configuration{% endif %}
{% if capabilities.config.write %}    PATCH {{ api_base_url }}/services/{service_id}/configuration{% endif %}
{% if capabilities.environment.read %}    GET {{ api_base_url }}/services/{service_id}/environment{% endif %}
{% if capabilities.environment.write %}    POST {{ api_base_url }}/services/{service_id}/environment
    DELETE {{ api_base_url }}/services/{service_id}/environment{% endif %}
{% if capabilities.secrets.read %}    GET {{ api_base_url }}/services/{service_id}/secrets{% endif %}
{% if capabilities.secrets.write %}    POST {{ api_base_url }}/services/{service_id}/secrets
    DELETE {{ api_base_url }}/services/{service_id}/secrets{% endif %}
{% if capabilities.endpoints.read %}    GET {{ api_base_url }}/services/{service_id}/endpoints{% endif %}
{% if capabilities.endpoints.write %}    POST {{ api_base_url }}/services/{service_id}/endpoints
    DELETE {{ api_base_url }}/services/{service_id}/endpoints{% endif %}
{% if capabilities.service_networks.read %}    GET {{ api_base_url }}/services/{service_id}/networks{% endif %}
{% if capabilities.service_networks.write %}    POST {{ api_base_url }}/services/{service_id}/networks
    DELETE {{ api_base_url }}/services/{service_id}/networks{% endif %}
{% if capabilities.config.read %}    GET {{ api_base_url }}/services/{service_id}/databases{% endif %}
{% if capabilities.config.write %}    POST {{ api_base_url }}/services/{service_id}/databases
    DELETE {{ api_base_url }}/services/{service_id}/databases{% endif %}
{% endif %}

{% if capabilities.services.read %}
## Revisions
    GET {{ api_base_url }}/services/{service_id}/revisions
    GET {{ api_base_url }}/services/{service_id}/revisions/{revision_id}
{% if capabilities.deployments.rollback %}    POST {{ api_base_url }}/services/{service_id}/revisions/{revision_id}/rollback{% endif %}
{% endif %}

{% if capabilities.shell.read or capabilities.shell.execute or capabilities.shell.replace or capabilities.shell.files_read or capabilities.shell.files_write %}
## Restricted shell
{% if capabilities.shell.read %}    GET {{ api_base_url }}/services/{service_id}/shell
    POST {{ api_base_url }}/services/{service_id}/shell/sessions
    POST {{ api_base_url }}/services/{service_id}/shell/sessions/{session_id}/close{% endif %}
{% if capabilities.shell.execute %}    POST {{ api_base_url }}/services/{service_id}/shell/sessions/{session_id}/commands{% endif %}
{% if capabilities.shell.replace %}    POST {{ api_base_url }}/services/{service_id}/shell/replace{% endif %}
{% if capabilities.shell.files_read or capabilities.shell.files_write %}    POST {{ api_base_url }}/services/{service_id}/shell/files{% endif %}
{% endif %}

## Common workflows

{% if capabilities.services.read %}
### Inspect services

    GET {{ api_base_url }}/services
{% endif %}
{% if capabilities.services.create and capabilities.plans.apply %}
### Create service from plan

1. Inspect the plan.
2. Inspect the user's Private Networks.
3. Supply an existing network or create one when permitted.
4. Call:

    POST {{ api_base_url }}/services/from-plan
{% endif %}
{% if capabilities.deployments.create and capabilities.deployments.upload and capabilities.deployments.start %}
### Deploy ZIP/source archive

1. Create deployment metadata.
2. Upload the ZIP.
3. Start the deployment.
4. Poll deployment status.
{% if capabilities.deployments.logs_read %}5. Read deployment logs.{% endif %}

    POST {{ api_base_url }}/deployments
    POST {{ api_base_url }}/deployments/{id}/upload
    POST {{ api_base_url }}/deployments/{id}/start
{% if capabilities.deployments.logs_read %}    GET  {{ api_base_url }}/deployments/{id}/logs{% endif %}

The current production deployment path supports ZIP/archive application deployment and database-native deployment. Git and existing-image inputs are not advertised as first-class Agent deployment sources.
{% endif %}
{% if capabilities.deployments.logs_read or capabilities.runtime_logs.read %}
### Diagnose a failed deployment

Deployment lifecycle logs and runtime service logs are intentionally separate.
{% if capabilities.deployments.logs_read %}
Deployment logs answer build/orchestration/lifecycle questions:

    GET {{ api_base_url }}/deployments/{id}/logs
{% endif %}
{% if capabilities.runtime_logs.read %}
Runtime service logs answer application/container questions:

    GET {{ api_base_url }}/services/{id}/logs
{% endif %}
Never merge these sources into one ambiguous stream.
{% endif %}
{% if capabilities.shell.execute %}
### Execute a command inside a service

1. Check shell capability.
2. Create or reuse an authorized restricted shell session.
3. Execute through the existing shell policy.
4. If the policy returns `CONFIRMATION_REQUIRED`, obtain explicit user authorization before retrying with `confirm=true`.
5. Return bounded stdout/stderr, exit code, duration and cwd.
{% endif %}

## Important rules

- Deployment logs and runtime service logs are different sources.
- Deployment IDs, release IDs, service IDs and revision IDs are distinct.
- Revisions are immutable; rollback uses the existing rollback boundary rather than mutating an old revision.
- Agent scopes are an upper bound; existing PassDeployer User authorization and ServiceShare action permissions still apply.
- Normal secret reads are metadata-only and masked. Never attempt to recover plaintext secret values from logs, configuration or errors.
- Shell execution is inside the authorized service runtime/container, never on the PassDeployer host.
- Existing forbidden binaries, shell-operator restrictions, path/workdir confinement, session TTL, output limits and confirmation behavior remain in force.
- Send `Idempotency-Key` when retrying supported mutating operations. Keys are scoped to the Agent and request shape and retained for 24 hours.
- Unsupported capabilities must not be assumed; re-check `/capabilities` before using an operation.

## Error handling

Structured errors may include `code`, `detail`, `request_id`, `retryable`, `failure_domain`, `visibility`, `resource_effect` and `certainty`.
Distinguish invalid input, authentication failure, insufficient scope, ServiceShare denial, resource not found, transient infrastructure failure, cancellation, confirmation required and unsupported capability before retrying.
