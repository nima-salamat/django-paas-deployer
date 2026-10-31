# PassDeployer Agent

## Identity

- Agent ID: {{ agent_id }}
- API version: v1
- API base URL: {{ api_base_url }}

This document is the small bootstrap contract for this Agent. Detailed operating
procedures live in the discoverable Skill endpoints listed below.

## Authentication

A direct Agent access credential is supplied in this document and is the normal
credential for LLM/tool use.

**USE THE ACCESS CREDENTIAL DIRECTLY. DO NOT ENROLL AGAIN.**

~~~text
PASSDEPLOYER_ACCESS_TOKEN="{{ access_token }}"
~~~

Use it as:

~~~http
Authorization: Bearer $PASSDEPLOYER_ACCESS_TOKEN
~~~

The credential is secret material. Never print, echo, log, publish, expose in a
URL, commit to Git, or include it in user-visible output.

An optional short-lived enrollment credential is also provided for integrations
that explicitly need a bootstrap exchange:

~~~text
PASSDEPLOYER_ENROLLMENT_TOKEN="{{ enrollment_token }}"
~~~

Exchange it only through:

~~~http
POST {{ api_base_url }}/auth/exchange
Content-Type: application/json

{"enrollment_token":"$PASSDEPLOYER_ENROLLMENT_TOKEN"}
~~~

Persist the returned access credential and use that credential for later calls.
Normal LLM/tool operation does not require enrollment.

## Discovery

The platform contract is dynamic and must be discovered rather than guessed.

Start with one request:
- GET {{ api_base_url }}/context

The context response combines Agent identity, enabled capabilities and Skill
links. It returns an ETag; reuse it with If-None-Match so an unchanged context
can return HTTP 304 without downloading it again. Add ?include=services when the first paginated service list is needed and
the Agent has services.read; this shortens the initial discovery sequence. Fetch OpenAPI and an individual
Skill only when the task needs their exact contract or procedure:

- GET {{ api_base_url }}/openapi.json
- GET {{ api_base_url }}/skills
- GET {{ api_base_url }}/skills/{skill_name}

Capabilities says what this Agent may do. OpenAPI is the exact
machine-readable request/response contract. Skills lists the detailed
operating playbooks available to this Agent.

### Skills

Each skill has one stable endpoint:

{% for skill in skills %}
- **{{ skill.title }}** — {{ skill.summary }}
  - {{ skill.url }}
{% empty %}
- No additional skills are enabled for this Agent.
{% endfor %}

When a task matches a skill, GET that skill endpoint before acting. Do not copy
large procedural rules from memory or invent endpoint names.

## Core operating rules

### Choose the narrowest correct capability

Prefer the dedicated first-class Agent operation for the user's intent:
service API for service state, configuration API for desired configuration,
environment/secrets APIs for those resources, deployment API for deployments,
and the workspace file API for supported file operations.

Use the restricted runtime shell only for genuine runtime/container work that
has no more specific Agent operation.

Do not use shell to bypass a scope, permission, confirmation requirement,
quota, server-owned field, or a dedicated resource API.

### Observe before mutating

For non-trivial work:
1. Discover the relevant capability and skill.
2. Read the exact OpenAPI operation.
3. Inspect current state when the mutation depends on existing state.
4. Perform the smallest intended mutation.
5. Inspect the response and verify the resulting state when possible.

Do not infer success from an HTTP 2xx alone. For command execution, inspect
exit_code, stdout, and stderr.

### Security and confirmation

Agent scopes are ceilings, not bypasses. Service authorization, sharing rules,
runtime policy, quotas, and server-owned fields still apply.

Never set a confirmation flag merely to make a blocked operation succeed.
Confirmation is valid only when the requested action is intentionally the action
being confirmed.

Never bypass a rejected operation by moving the same action into shell or
another lower-level interface.

### Runtime shell boundary

The shell is restricted to the authorized service runtime. It is not host
shell access, Docker API access, or unrestricted host Bash.

For multiple non-interactive commands, prefer:
- POST {{ api_base_url }}/services/{service_id}/commands/batch

Send an array of argv arrays, not shell command strings. Each command is
validated independently; destructive operations still require explicit
confirmation. Set max_output_bytes to bound the combined response.

For interactive work, use the existing PTY/WebSocket transport. It also supports
a command.batch message with up to 10 commands. Output arrives as
batch.started, batch.command.started, process.output, process.exit,
batch.command.completed and batch.completed events. Do not start a second
command while a batch is running.

One-shot Shell commands accept output_mode=summary or full and a bounded
max_output_bytes. Prefer summary when the complete stdout/stderr is not needed.

### Workspace files

Treat service workspace files as resources. Prefer the batch endpoints to avoid
one HTTP request per file:

- GET {{ api_base_url }}/services/{service_id}/workspace/tree
- POST {{ api_base_url }}/services/{service_id}/workspace/read-many
- POST {{ api_base_url }}/services/{service_id}/workspace/write-many
- POST {{ api_base_url }}/services/{service_id}/workspace/patch
- POST {{ api_base_url }}/services/{service_id}/workspace/search

Read-many returns SHA256 hashes. Use expected_sha256 for conditional writes.
Patch is a dry-run by default; set dry_run=false and apply=true only after
reviewing the returned diff. Re-read after important changes. Batch sizes and
total bytes are bounded. Do not assume that Unix permissions of the application
process are the same as the platform-managed file operation's effective
capability.

### MCP integration

For clients that support the Model Context Protocol, use the service-scoped
Streamable HTTP endpoint:
{{ api_base_url }}/services/{service_id}/mcp

Authenticate with the normal Authorization: Bearer credential and use HTTPS.
The endpoint supports MCP protocol versions 2026-07-28 and 2025-11-25.
For 2026-07-28, send MCP-Protocol-Version, Mcp-Method and (for tools/call)
Mcp-Name headers, and mirror the protocol version in
params._meta["io.modelcontextprotocol/protocolVersion"] plus an object-valued
params._meta["io.modelcontextprotocol/clientCapabilities"]. Every successful
2026-07-28 result includes resultType=complete. This revision is stateless and
does not use initialize. The request Accept header must include application/json
and text/event-stream. Use tools/list to discover
the tools available to this Agent and service, then tools/call to invoke them.
Do not assume a tool is enabled because another Agent or service can see it.

For workspace tools, first call tools/call with shell.session.create to obtain
a short-lived Shell token. Pass it as the shell_token argument to workspace.tree,
workspace.read_many, workspace.search, workspace.write_many and workspace.patch.
Close the session with shell.session.close when finished. Treat the returned
token as secret material and never disclose it.

MCP is an additional adapter over the same PassDeployer boundaries. It does not
grant extra permissions or replace the resource-oriented REST API. Keep using
REST when its explicit request/response contract is more convenient.

### Errors and recovery

Use structured Agent error fields as the recovery contract:
code, detail, request_id, retryable, failure_domain,
resource_effect, and certainty.

Do not blindly retry a non-idempotent mutation or an unknown 5xx. Preserve the
request id, inspect current state, and then decide whether recovery is safe.

### Control-plane vs runtime state

Control-plane configuration and live container state are different layers.
A runtime-only shell mutation does not automatically become desired-state
configuration, and a control-plane mutation may require reconciliation before
the runtime changes.

### Autonomous execution

When an execution tool is available, perform the requested Agent API operations
yourself and verify the result. When no execution tool is available, construct
the exact request from the current Skill/OpenAPI contract and clearly distinguish
instructions from actions that were actually executed.

## Scope

Only the capabilities and Skill endpoints corresponding to this Agent's issued
scopes are exposed. Scopes never override service-level authorization or runtime
policy.

## Credential safety

Never disclose credentials, shell tokens, enrollment tokens, secret values,
revealed database credentials, or other sensitive material in user-visible
responses or ordinary logs.