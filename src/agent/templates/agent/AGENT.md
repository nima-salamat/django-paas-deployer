# PassDeployer Agent

## Identity

- Agent ID: {{ agent_id }}
- API version: v1
- API base URL: {{ api_base_url }}

This file is generated for this specific Agent. The operation list below is derived
from the same contract registry used by runtime scope enforcement and OpenAPI.

## Authentication and enrollment

PASSDEPLOYER_ENROLLMENT_TOKEN="{{ enrollment_token }}"

Exchange it exactly once:

    POST {{ api_base_url }}/auth/exchange
    {"enrollment_token":"$PASSDEPLOYER_ENROLLMENT_TOKEN"}

The exchange invalidates the enrollment credential and returns a normal Bearer
access token. Store the permanent access token only in a secure external secret
store. Never put a permanent token in a URL, repository, source file, or log.

## Issued scopes

{% for scope in scopes %}- `{{ scope }}`
{% empty %}- No operational scopes are enabled.
{% endfor %}

## Enabled API operations

Only operations that satisfy this Agent's issued scopes are listed.

| Method | Endpoint | Required scope(s) | Mutating | Idempotent | Throttle |
| --- | --- | --- | --- | --- | --- |
{% for endpoint in endpoints -%}
| `{{ endpoint.method }}` | `{{ endpoint.path }}` | `{{ endpoint.requirements }}` | {{ endpoint.mutating|yesno:"yes,no" }} | {{ endpoint.idempotent|yesno:"yes,no" }} | `{{ endpoint.throttle }}` |
{% empty -%}
| — | — | none | no | no | — |
{% endfor %}

## Discovery

Machine-readable capabilities:

    GET {{ api_base_url }}/capabilities

OpenAPI:

    GET {{ api_base_url }}/openapi.json

## Operational rules

- Agent scopes are an upper bound. Existing PassDeployer User authorization and
  ServiceShare permissions remain authoritative.
- Deployment lifecycle logs and runtime service logs are separate sources.
- Revisions are immutable; rollback creates a new deployment through the
  existing rollback boundary.
- Secret values are never returned as normal API metadata. Use secret resources
  rather than placing sensitive values in ordinary configuration.
- Shell access remains inside the authorized service runtime/container. The
  host shell, Docker socket, and raw Docker API are not part of this contract.
- Restricted shell rules, path confinement, session TTLs, output limits and
  destructive-command confirmation remain enforced by the underlying shell
  subsystem.
- Send an `Idempotency-Key` on operations marked idempotent. Keys are scoped
  to this Agent and to the complete request shape.
- Re-check `/capabilities` when building an automation because the issued
  scopes can differ between Agents.
- Supported first-class deployment inputs are archive/ZIP and database-native
  deployment. Git and existing-image deployment are not part of this contract.

## Common workflows

### Create from a plan

Use the plan-application operation only when both `services.create` and
`plans.apply` are issued.

### Deploy an archive

1. Create deployment metadata.
2. Upload the ZIP archive.
3. Start the deployment.
4. Poll deployment status.
5. Read deployment lifecycle logs when the logs scope is enabled.

### Diagnose a failure

Use deployment logs for lifecycle/build/orchestration events and runtime logs
for application/container output. Do not merge the two streams.

### Shell

Create a restricted service-container session, then execute commands using the
shell token returned for that session. Destructive operations may require an
explicit confirmation response from the underlying shell policy.

## Error handling

Structured errors may include `code`, `detail`, `request_id`, `retryable`,
`failure_domain`, `visibility`, `resource_effect`, and `certainty`.
Treat permission failures, conflicts, invalid requests, transient failures,
confirmation requirements and unsupported capabilities as different conditions.
