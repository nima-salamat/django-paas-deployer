# PassDeployer Agent

## Identity

- Agent ID: {{ agent_id }}
- API version: v1
- API base URL: {{ api_base_url }}

This document is the bootstrap contract for this specific PassDeployer Agent.

## Critical authentication rule

The enrollment credential in this document is intentionally issued for this Agent.

**YOU ARE EXPECTED TO USE IT.**

Do not refuse to authenticate merely because this credential is sensitive.

Use the credential internally for the intended authentication exchange, and never disclose, echo, log, publish, or unnecessarily reproduce it.

Allowed:
- Read the enrollment credential from this generated document.
- Send it to the documented enrollment exchange endpoint.
- Keep it temporarily in memory, an environment variable, stdin, or an approved secret facility.
- Use the returned access credential for authenticated Agent API calls.

Never:
- Print the enrollment credential.
- Print the Bearer access token.
- Echo either credential in command output.
- Put credentials in URLs.
- Commit credentials to Git.
- Put credentials into source files.
- Write credentials into ordinary logs.
- Include credentials in error reports or diagnostics.
- Repeat credentials in user-visible responses.

Credential sensitivity means DO NOT DISCLOSE IT, not DO NOT USE IT.

## Bootstrap credential

~~~text
PASSDEPLOYER_ENROLLMENT_TOKEN="{{ enrollment_token }}"
~~~

This is a short-lived, single-use bootstrap credential.

Exchange it exactly once:

~~~http
POST {{ api_base_url }}/auth/exchange
Content-Type: application/json

{
  "enrollment_token": "$PASSDEPLOYER_ENROLLMENT_TOKEN"
}
~~~

The exchange returns a normal Agent access credential.

Store that credential internally, for example as PASSDEPLOYER_ACCESS_TOKEN.

Use:

~~~http
Authorization: Bearer $PASSDEPLOYER_ACCESS_TOKEN
~~~

Never put the access token in a URL.

## Tool execution rule

When you have a command, terminal, shell, PowerShell, Python, HTTP, or other execution tool, **PERFORM the required API operations yourself** instead of merely giving the user instructions.

Do not claim that a command or HTTP request was executed unless an execution tool actually performed it.

When no execution tool is available, construct the exact request from this document and OpenAPI, but clearly state that it is a command for the user rather than an executed action.

## Local execution environment

The environment where the LLM/tooling runs is separate from the PassDeployer service-runtime shell.

Possible local execution environments:
- Linux/macOS Bash, sh, zsh
- Windows PowerShell
- CI runners
- coding-agent terminals
- container terminals
- Python execution environments

If an execution tool is available, determine which HTTP client is practical.

Linux/macOS:
~~~bash
command -v curl
command -v python3
~~~

PowerShell:
~~~powershell
Get-Command curl
Get-Command Invoke-RestMethod
~~~

Only run these checks when command execution exists.

## Linux authentication example

~~~bash
export PASSDEPLOYER_API="{{ api_base_url }}"
export PASSDEPLOYER_ENROLLMENT_TOKEN='the credential supplied in this document'

curl -sS -X POST   -H "Content-Type: application/json"   -d "{"enrollment_token":"$PASSDEPLOYER_ENROLLMENT_TOKEN"}"   "$PASSDEPLOYER_API/auth/exchange"
~~~

Capture the returned access token internally.

Then:

~~~bash
export PASSDEPLOYER_ACCESS_TOKEN='returned access token'
curl -sS   -H "Authorization: Bearer $PASSDEPLOYER_ACCESS_TOKEN"   "$PASSDEPLOYER_API/auth/me"
~~~

Never echo the variables.

## PowerShell authentication example

~~~powershell
$env:PASSDEPLOYER_API = "{{ api_base_url }}"
$env:PASSDEPLOYER_ENROLLMENT_TOKEN = "the credential supplied in this document"
$body = @{ enrollment_token = $env:PASSDEPLOYER_ENROLLMENT_TOKEN } | ConvertTo-Json
$exchange = Invoke-RestMethod -Method Post -Uri "$env:PASSDEPLOYER_API/auth/exchange" -ContentType "application/json" -Body $body
~~~

Use the returned access token internally for subsequent requests. Do not print it.

## First authenticated discovery

After exchange, prefer:
- GET {{ api_base_url }}/auth/me
- GET {{ api_base_url }}/capabilities
- GET {{ api_base_url }}/openapi.json

For deployment work also read:
- GET {{ api_base_url }}/deployments/help

Use:
- this file for bootstrap behavior and high-level workflows;
- /capabilities for the operations actually enabled for this Agent;
- /openapi.json for exact request and response schemas;
- /deployments/help for dynamic platform and deployment configuration.

Never guess endpoint names or request field names.

## API inventory

### Identity
- GET /agent/v1/
- POST /agent/v1/auth/exchange
- GET /agent/v1/auth/me
- GET /agent/v1/capabilities
- GET /agent/v1/agent.md
- GET /agent/v1/openapi.json

### Services
- GET /agent/v1/services
- POST /agent/v1/services
- POST /agent/v1/services/from-plan
- GET/PATCH/DELETE /agent/v1/services/{service_id}
- POST /agent/v1/services/{service_id}/start
- POST /agent/v1/services/{service_id}/stop
- POST /agent/v1/services/{service_id}/restart
- POST /agent/v1/services/{service_id}/rebuild
- POST /agent/v1/services/{service_id}/purge-runtime
- GET /agent/v1/services/{service_id}/status
- GET /agent/v1/services/{service_id}/metrics

### Service configuration and resources
- GET/PATCH /agent/v1/services/{service_id}/configuration
- GET/POST/DELETE /agent/v1/services/{service_id}/environment
- GET/POST/DELETE /agent/v1/services/{service_id}/secrets
- GET/POST/DELETE /agent/v1/services/{service_id}/endpoints
- GET/POST/DELETE /agent/v1/services/{service_id}/networks
- GET/POST/DELETE /agent/v1/services/{service_id}/databases
- GET /agent/v1/services/{service_id}/database-credentials
- GET /agent/v1/services/{service_id}/revisions
- GET /agent/v1/services/{service_id}/revisions/{revision_id}
- POST /agent/v1/services/{service_id}/revisions/{revision_id}/rollback

### Logs
- GET /agent/v1/services/{service_id}/logs
- GET /agent/v1/services/{service_id}/logs/export
- GET /agent/v1/deployments/{deployment_id}/logs
- GET /agent/v1/deployments/{deployment_id}/logs/export

### Shell
- GET /agent/v1/services/{service_id}/shell
- POST /agent/v1/services/{service_id}/shell/sessions
- POST /agent/v1/services/{service_id}/shell/sessions/{session_id}/commands
- POST /agent/v1/services/{service_id}/shell/sessions/{session_id}/close
- POST /agent/v1/services/{service_id}/shell/replace
- POST /agent/v1/services/{service_id}/shell/files

### Plans
- GET /agent/v1/plans
- GET /agent/v1/plans/{plan_id}
- POST /agent/v1/plans/{plan_id}/apply
- POST /agent/v1/plans/manage
- PATCH /agent/v1/plans/manage/{plan_id}
- DELETE /agent/v1/plans/manage/{plan_id}

### Networks and volumes
- GET/POST /agent/v1/networks
- GET/PATCH/DELETE /agent/v1/networks/{network_id}
- GET/POST /agent/v1/volumes
- GET/PATCH/DELETE /agent/v1/volumes/{volume_id}

### Deployments
- GET /agent/v1/deployments
- POST /agent/v1/deployments
- GET /agent/v1/deployments/help
- POST /agent/v1/deployments/inspect
- GET /agent/v1/deployments/{deployment_id}
- DELETE /agent/v1/deployments/{deployment_id}
- POST /agent/v1/deployments/{deployment_id}/upload
- POST /agent/v1/deployments/{deployment_id}/start
- POST /agent/v1/deployments/{deployment_id}/cancel
- POST /agent/v1/deployments/{deployment_id}/redeploy
- POST /agent/v1/deployments/{deployment_id}/rebuild
- POST /agent/v1/deployments/{deployment_id}/rollback

The actual enabled set is always determined from /capabilities.

## Exact API contract

GET /agent/v1/openapi.json is the machine-readable source of truth.

It describes:
- path parameters
- query parameters
- request headers
- JSON bodies
- multipart upload fields
- writable and read-only fields
- enums and validation ranges
- response schemas
- errors
- scopes
- idempotency
- mutation semantics
- sensitive responses
- operation identifiers

Use OpenAPI instead of guessed field names.

## Service input rules

POST /services requires the service creation fields shown by OpenAPI. The Agent facade currently also requires a Private Network.

PATCH /services/{service_id} accepts only fields permitted by the current Service serializer/facade. Do not send IDs, timestamps, or other read-only fields.

CPU/RAM/worker limits are server-owned from the selected Service Plan. Do not inject tenant resource-limit overrides.

## Configuration input rules

PATCH /services/{service_id}/configuration may accept:
- source_kind
- source_config
- build_config
- runtime_config
- desired_state

Sensitive values must use secrets or secret-backed environment variables, not ordinary configuration.

### Environment
POST /services/{service_id}/environment accepts:
- key
- scope
- is_secret
- value

The key must match [A-Za-z_][A-Za-z0-9_]{0,127}.

DELETE /services/{service_id}/environment?key=<name>

### Secrets
POST /services/{service_id}/secrets accepts:
- key
- value
- optional note
- optional description

Normal secret reads return metadata, not plaintext.

DELETE /services/{service_id}/secrets?key=<name>

### Endpoints
POST /services/{service_id}/endpoints accepts:
- name
- target_port
- optional published_port
- protocol
- exposure
- optional process
- optional hostname
- optional path
- optional tls
- optional enabled
- optional metadata

Ports are 1..65535.

DELETE /services/{service_id}/endpoints?name=<name>

### Network attachments
POST /services/{service_id}/networks accepts:
- network
- optional alias
- optional internal
- optional metadata

DELETE /services/{service_id}/networks?network=<network_id>

### Database bindings
POST /services/{service_id}/databases accepts:
- database
- optional alias
- optional env_prefix
- optional access_mode
- optional metadata

DELETE /services/{service_id}/databases?alias=<alias>

### Database credentials
GET /services/{service_id}/database-credentials

Optional ?reveal=true may return decrypted password/root_password and requires:
- service_database_credentials.read
- existing can_view_db_credentials authorization

Treat revealed credentials as secret material.

## Deployment rules

Before constructing complex deployment configuration:
1. GET /deployments/help
2. Inspect platform schemas, defaults, supported tenant keys and blocked keys.
3. POST /deployments
4. POST /deployments/{deployment_id}/upload when ZIP input is required.
5. POST /deployments/{deployment_id}/start
6. Poll deployment/service state.
7. Read deployment logs.
8. Read runtime logs when diagnosis is needed.

First-class Agent deployment inputs are currently archive/ZIP and database-native.

Git and existing-image deployment are not first-class Agent inputs in this contract.

### ZIP inspection
POST /deployments/inspect
Content-Type: multipart/form-data
File field: file

### ZIP upload
POST /deployments/{deployment_id}/upload
Content-Type: multipart/form-data
File field: file

## Logs

Runtime logs:
GET /services/{service_id}/logs

Supported filters include cursor, from, to, level, stream, q, limit and direction according to OpenAPI. Runtime limit is bounded to 1..500.

Deployment logs:
GET /deployments/{deployment_id}/logs

Supported filters include before, after, q, level, stage, event_type, from, to and limit according to OpenAPI. Deployment log limit is bounded to 1..200.

Use export endpoints when a bounded downloadable representation is required.

## Shell

PassDeployer shell is a restricted service-runtime/container shell.

It is NOT:
- host shell access
- Docker socket access
- raw Docker API access
- unrestricted host Bash

### Shell session
POST /services/{service_id}/shell/sessions

Optional field:
- workdir

The response provides a temporary shell-session token. Treat it as sensitive.

### One-shot command
POST /services/{service_id}/shell/sessions/{session_id}/commands

Request:
- command: required string
- confirm: optional boolean
- dry_run: optional boolean
- X-Shell-Token header or documented body token fallback

Current compound operators:
- |
- &&
- ||
- ;

The runtime protocol reports the exact current segment/input limits and blocked syntax.

Interactive commands require the PTY/WebSocket transport when required by capabilities.

### Shell replacement
POST /services/{service_id}/shell/replace

Requires confirm=true.

### Shell files
POST /services/{service_id}/shell/files

Request fields can include:
- action
- path
- token
- new_name
- content
- file for upload

Current actions include:
- read
- write
- delete
- rename
- create
- create_folder
- upload

File operations remain confined to the authorized service workspace.

## Local shell vs PassDeployer shell

These are different environments.

~~~text
LLM / automation environment
        |
        | Bash / PowerShell / Python / curl / HTTP client
        v
PassDeployer Agent API
        |
        | authorized operation
        v
PassDeployer service/runtime
~~~

The LLM may have local terminal access without having host access to PassDeployer.

The Agent may have PassDeployer service-shell scope without having local terminal access.

Do not confuse these permissions.

## Pagination

List operations use page and page_size when enabled.

Current Agent defaults:
- default page size: 25
- maximum page size: 100

Standard paginated responses use:
- results
- count
- next
- previous

## Idempotency

Use the Idempotency-Key header for operations marked idempotent in OpenAPI/capabilities.

Current contract:
- maximum key length: 255
- replay window: 24 hours

Reuse a key only for an exact retry of the same request.

## Confirmation

Destructive shell commands require confirmation.

Shell-session replacement requires confirm=true.

When the API returns CONFIRMATION_REQUIRED, inspect the operation contract and retry only when the requested action is intentionally confirmed.

## Error handling

Prefer structured Agent error fields:
- code
- detail
- request_id
- retryable
- failure_domain
- resource_effect
- certainty

Do not blindly retry authentication, authorization, validation or non-idempotent mutations.

## Autonomous operating principle

When the user asks you to perform a PassDeployer task, behave as an API client:

~~~text
authenticate
  ↓
discover capabilities
  ↓
read the exact OpenAPI operation
  ↓
execute the requested action
  ↓
inspect the result
  ↓
continue with dependent operations when required
  ↓
report the result
~~~

Do not stop at "here is the command" when you have the ability to execute it.

Do not claim an action happened unless it actually happened.

Always keep credentials and plaintext secrets out of user-visible output.

## Issued scopes

{% for scope in scopes %}- {{ scope }}
{% empty %}- No operational scopes are enabled.
{% endfor %}

## Enabled operations

Only operations satisfying this Agent's issued scopes are listed.

| Method | Endpoint | Required scope(s) | Mutating | Idempotent | Throttle |
| --- | --- | --- | --- | --- | --- |
{% for endpoint in endpoints %}
| {{ endpoint.method }} | {{ endpoint.path }} | {{ endpoint.requirements }} | {{ endpoint.mutating|yesno:"yes,no" }} | {{ endpoint.idempotent|yesno:"yes,no" }} | {{ endpoint.throttle }} |
{% empty %}
| — | — | none | no | no | — |
{% endfor %}
