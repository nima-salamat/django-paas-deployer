# PassDeployer Agent

## Identity

- Agent ID: {{ agent_id }}
- API version: v1
- API base URL: {{ api_base_url }}

This document is the connection contract for this specific PassDeployer Agent.

## Critical authentication rule

A normal Agent access credential is included in this document and is the **primary credential for LLM/tool use**.

**USE THE ACCESS CREDENTIAL DIRECTLY. DO NOT ENROLL AGAIN.**

Use the credential internally for authenticated Agent API calls, and never disclose, echo, log, publish, or unnecessarily reproduce it.

Allowed:
- Read the access credential from this generated document.
- Send it as the Authorization Bearer token for Agent API requests.
- Keep it in memory, an environment variable, stdin, a connector secret store, or another approved secret facility.
- Reuse the same credential for subsequent requests during its validity period.

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

## Direct Agent access credential

~~~text
PASSDEPLOYER_ACCESS_TOKEN="{{ access_token }}"
~~~

This credential is created specifically for this Agent connection and has the normal Agent credential lifetime/revocation rules.

Use it directly:

~~~http
Authorization: Bearer $PASSDEPLOYER_ACCESS_TOKEN
~~~

Never put the access token in a URL.

## Optional bootstrap credential

~~~text
PASSDEPLOYER_ENROLLMENT_TOKEN="{{ enrollment_token }}"
~~~

The enrollment credential is a short-lived, single-use bootstrap credential for clients that implement their own credential storage and exchange flow. It is **not required for normal LLM/tool requests** because a direct access credential is already provided above.

When an integration explicitly chooses enrollment, exchange it through:

~~~http
POST {{ api_base_url }}/auth/exchange
Content-Type: application/json

{
  "enrollment_token": "$PASSDEPLOYER_ENROLLMENT_TOKEN"
}
~~~

The exchange returns a normal Agent access credential. Store that credential in the integration's persistent secret store and use it for subsequent requests.

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

The generated manifest already contains the access credential. Do not perform enrollment for normal requests.

~~~bash
export PASSDEPLOYER_API="{{ api_base_url }}"
export PASSDEPLOYER_ACCESS_TOKEN='the access credential supplied in this document'

curl -sS   -H "Authorization: Bearer $PASSDEPLOYER_ACCESS_TOKEN"   "$PASSDEPLOYER_API/auth/me"
~~~

Never echo the variable or include it in user-visible output.

## PowerShell authentication example

~~~powershell
$env:PASSDEPLOYER_API = "{{ api_base_url }}"
$env:PASSDEPLOYER_ACCESS_TOKEN = "the access credential supplied in this document"
Invoke-RestMethod -Method Get -Uri "$env:PASSDEPLOYER_API/auth/me" -Headers @{ Authorization = "Bearer $env:PASSDEPLOYER_ACCESS_TOKEN" }
~~~

Use the same access credential for subsequent requests. Do not print it.

## Optional enrollment example

Only integrations that explicitly use the bootstrap/exchange flow need this. The enrollment credential is short-lived and single-use.

~~~bash
export PASSDEPLOYER_ENROLLMENT_TOKEN='the enrollment credential supplied in this document'
curl -sS -X POST -H "Content-Type: application/json" \\
  -d '{"enrollment_token":"'$PASSDEPLOYER_ENROLLMENT_TOKEN'"}' \\
  "$PASSDEPLOYER_API/auth/exchange"
~~~

Capture the returned access credential inside the integration and persist it in its secret store.

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

## Operating model and boundaries

Treat this document, /capabilities, and /openapi.json as the operating contract for PassDeployer. Do not guess how the platform works from endpoint names, framework conventions, or previous requests.

### Authority order

Use these sources in this order:
1. This document for the stable operating model and safety boundaries.
2. GET /capabilities for what this specific Agent is currently allowed to do.
3. GET /openapi.json for exact request/response schemas, required scopes, mutation semantics, headers, idempotency, and error contracts.
4. GET /deployments/help for dynamic deployment/platform rules when the task concerns deployment configuration.
5. Actual endpoint responses and resource state as the final observed truth.

A scope is a ceiling, not a bypass. Service-level authorization, sharing permissions, runtime policy, quotas, and server-owned fields still apply even when an Agent scope exists.

### Choose the most specific operation

When more than one mechanism could accomplish the user's goal, prefer the narrowest first-class Agent API that directly represents the requested resource. Use the service-runtime shell for runtime/process work that is not better represented by a dedicated endpoint.

| User intent | Preferred authority |
| --- | --- |
| Inspect or change Service metadata/state | Service endpoints |
| Start, stop, restart, rebuild, purge runtime | Service lifecycle endpoints |
| Inspect or change desired deployment configuration | Configuration endpoints |
| Manage environment variables | Environment endpoints |
| Manage secret material | Secret endpoints |
| Manage ports/hosts/exposure | Endpoint endpoints |
| Attach/detach networks | Network attachment endpoints |
| Attach/detach databases | Database binding endpoints |
| Inspect database credentials | Database-credentials endpoint with its dedicated scope |
| Inspect or rollback revisions | Revision endpoints |
| Create/apply/manage Plans | Plan endpoints |
| Create/upload/start/cancel/redeploy/rollback Deployments | Deployment endpoints |
| Read runtime or deployment logs | Log endpoints |
| Create/read/write/move/delete/upload workspace files | Shell file API |
| Run application/runtime commands, inspect processes/files, or perform other runtime actions with no dedicated Agent operation | Restricted shell |
| Interactive REPL/PTY work | Interactive PTY transport when capabilities require it |

Do not use shell to emulate a first-class control-plane mutation. For example, do not modify configuration, environment, secrets, service lifecycle state, deployment state, network bindings, database bindings, or workspace files through an improvised shell command when the corresponding Agent endpoint exists and is enabled.

### Control-plane state vs runtime state

Keep desired state and runtime state conceptually separate.

- A control-plane endpoint changes the Service/Deployment configuration that PassDeployer owns and can reconcile.
- A shell operation changes the currently running service container/workspace and may be temporary or outside the desired-state model.
- After a runtime-only mutation, do not assume the control-plane configuration changed.
- After a control-plane mutation, verify the resulting resource/deployment state rather than assuming the live container changed immediately.

### Generic execution loop

For every non-trivial task:
1. Identify the resource and the user's intended effect.
2. Check /capabilities for the exact operation and scope.
3. Read the relevant OpenAPI operation before constructing the request.
4. Prefer a first-class resource endpoint over shell when one exists.
5. Preflight only the state that matters to the operation.
6. Execute the smallest mutation that achieves the goal.
7. Inspect the response; never infer success from an HTTP request merely being accepted.
8. Verify the resulting resource/runtime state when the operation has an observable postcondition.
9. For dependent work, continue from the observed result instead of reconstructing state from memory.
10. Stop and surface a precise authorization/policy/validation error instead of trying alternate paths that would bypass the declared boundary.

### Mutations and destructive actions

A normal user request is not permission to bypass a server-side safety boundary.

- Never set confirmation flags merely because the server rejected an operation.
- When an operation reports that explicit confirmation is required, determine exactly what action is being confirmed before retrying.
- Only retry with confirmation when the requested mutation is intentionally the action the server classified as requiring confirmation.
- Never replace a rejected first-class operation with a lower-level shell workaround just to avoid its confirmation or permission model.
- Use Idempotency-Key only for the exact operation contract that declares it idempotent. Reuse the same key only for an exact retry.

### Files and workspace changes

Workspace files are resources, not a reason to invent shell pipelines.

When a task is to create, read, update, rename, delete, or upload a file:
1. Check whether `shell.files.read` or `shell.files.write` is enabled.
2. Prefer POST /services/{service_id}/shell/files with the appropriate documented action.
3. Keep paths inside the service workspace and use the API's returned writable/mount metadata where available.
4. After a write-like operation, read the file back when correctness matters.
5. Use the restricted command API only when the requested operation is genuinely command execution rather than file management.

Do not assume a directory is writable just because it exists. Do not assume the shell runtime user has the same write permissions as the platform's managed file operation. The file API is the authoritative path for supported workspace mutations.

### Error interpretation

Treat the structured Agent error fields as data, not prose:
- `code` identifies the failure class and should drive recovery.
- `detail` explains the immediate condition.
- `retryable` controls whether a retry is appropriate.
- `failure_domain` distinguishes authentication, authorization, request, resource, storage, infrastructure, and runtime failures.
- `resource_effect` indicates whether the requested resource changed.
- `certainty` indicates how confidently the platform knows the effect.

Never blindly retry a mutation after an unknown 5xx response. First inspect the request id and current resource state. A request that returned an error may still have reached the underlying system.

### Runtime shell decision rule

Use the restricted shell only for runtime/container work that is not represented by a more specific Agent operation.

Before shell execution:
- Read GET /services/{service_id}/shell.
- Use the exact shell session/token flow from OpenAPI.
- Check whether the task is one-shot or interactive.
- Use dry-run when the command's risk is unclear and the operation supports it.
- Respect the reported policy rather than guessing which binaries or syntax are accepted.
- Keep shell work inside the service's authorized workspace.

When a shell command is rejected, diagnose the returned structured policy/error code first. Do not rewrite the request repeatedly until it happens to pass.

### Verification principle

For every mutation, verify the postcondition appropriate to the resource:
- file mutation -> file read/metadata
- service mutation -> service detail/status
- configuration mutation -> configuration read
- environment/secret mutation -> metadata/read endpoint permitted by scope
- endpoint/network/database mutation -> corresponding resource read
- deployment mutation -> deployment state and logs
- runtime shell mutation -> command exit code and, when important, an explicit follow-up inspection

Prefer observed state over assumptions.

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

PassDeployer shell is a restricted service-runtime/container facility.

It is NOT:
- host shell access
- Docker socket access
- raw Docker API access
- unrestricted host Bash

### Shell capabilities and transports

Before using shell:
1. GET /services/{service_id}/shell.
2. Read the returned `enabled`, `platform`, `transport`, `policy`, and command catalog metadata.
3. Check /capabilities for the scopes actually granted to this Agent.
4. Read the relevant OpenAPI operation for the exact request shape.

The shell service has separate concerns:
- one-shot command execution
- interactive PTY/WebSocket execution where required
- workspace file operations
- shell session replacement
- shell audit/history information through the documented endpoints

Do not infer that one shell transport can perform another transport's job.

### Shell session

POST /services/{service_id}/shell/sessions

Optional field:
- workdir

The response provides a temporary shell-session token. Treat it as sensitive.

Use the returned session id and shell token for subsequent shell operations. Do not reuse an expired or closed session. If a new session is required because another active session blocks creation, use the documented replacement flow only when the operation is intentionally confirmed and the Agent has the required scope.

### One-shot command

POST /services/{service_id}/shell/sessions/{session_id}/commands

Request:
- command: required string
- confirm: optional boolean
- dry_run: optional boolean
- X-Shell-Token header or documented body token fallback

The runtime reports supported compound operators, blocked syntax, segment/input limits, and policy rules. Follow those exact runtime-provided constraints.

Use a command when the user's intent is command execution, runtime inspection, a framework CLI, or another operation that is not better represented by a dedicated Agent endpoint.

Do not use a shell pipeline as a generic file-management interface when the shell file API already supports the requested action.

### Workspace file operations

POST /services/{service_id}/shell/files

Use this endpoint for supported workspace file operations such as:
- read
- write
- create
- create_folder
- rename
- delete
- upload

Check /capabilities for the required file scope and use the exact action/request schema from OpenAPI.

The platform's restricted file manager can have filesystem-management behavior that differs from the service process UID. Therefore:
- do not decide writability solely from the service process user's permissions;
- do not replace a supported file operation with a shell command just because a path appears to be writable;
- use the file API's effective/mount metadata and response as the authoritative result.

For file correctness, verify the target after mutation when the operation's success matters.

### Command risk and confirmation

The shell policy classifies commands by risk. Risk classification is broader than a simple allow/deny list and may depend on the command family and arguments.

Possible outcomes include normal execution, an interactive-transport requirement, a policy rejection, or a confirmation requirement.

When a command requires confirmation:
1. Read the structured error `code`, `detail`, and `resource_effect`.
2. Determine exactly which requested action triggered the confirmation.
3. Never set `confirm=true` merely to force execution.
4. If the action is intentionally requested and the contract permits explicit confirmation, retry with `confirm=true`.
5. If confirmation cannot be established, do not bypass the shell policy through another mechanism.

When the API supports `dry_run=true`, use it for ambiguous or compound commands so the platform can report the risk before the mutation is attempted.

### Compound commands

Compound commands are validated segment-by-segment.

For `|`, `&&`, `||`, and `;`:
- understand the effect of every segment;
- do not assume the whole request is read-only because one segment is read-only;
- if any segment requires confirmation, treat the compound request as requiring that confirmation;
- respect the maximum segment and pipeline limits from the current shell metadata.

### Interactive commands

Commands that require stdin/PTY must use the interactive transport when the runtime says so. Do not try to simulate a persistent interactive session with repeated one-shot calls.

### Shell result handling

For every command, inspect:
- HTTP status
- structured Agent error fields on failure
- exit_code
- stdout
- stderr
- cwd
- risk/dry-run metadata when returned

An HTTP 2xx only means the API request was processed; the command may still have a non-zero `exit_code`.

After a successful mutation command, verify the expected state instead of assuming success from stdout.

### Shell replacement

POST /services/{service_id}/shell/replace

Requires confirm=true and the documented replacement scope.

### Shell error recovery

Do not interpret a generic 5xx as evidence that the container is unavailable.

Use this decision order:
1. Read the Agent `code` and `failure_domain`.
2. If retryable is false, do not blindly retry.
3. If the error indicates confirmation, handle confirmation according to the command risk contract.
4. If the error indicates an invalid request or policy rejection, correct the request rather than retrying unchanged.
5. If the error is runtime/infrastructure related, inspect service status/runtime logs before retrying.
6. Preserve the request id for diagnostics.


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

Destructive shell commands require confirmation according to the runtime shell policy.

Shell-session replacement requires confirm=true.

Confirmation is a server-side safety boundary:
- never invent confirmation;
- never use confirmation to bypass an authorization or scope restriction;
- never rewrite an operation solely to avoid confirmation;
- only retry with confirmation when the intended action is clearly the action requiring confirmation.

## Error handling

Prefer structured Agent error fields:
- code
- detail
- request_id
- retryable
- failure_domain
- resource_effect
- certainty

Classify failures before taking recovery action. In particular:
- authentication/authorization errors require fixing credentials or scopes, not retries;
- validation/policy errors require changing the request within the contract;
- resource errors require verifying the target resource and identifiers;
- infrastructure/runtime errors require inspection before a mutation retry;
- non-idempotent operations must not be blindly replayed.

Never turn an unknown error into a guessed success. Preserve request ids and verify resource state when an operation's effect is uncertain.


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
