# Git Hosting and PaaS Source Deployment — Feasibility and Design Proposal

**Status:** Architecture proposal; not implemented by this document  
**Reviewed against:** `master` of `django-paas-deployer` and `main` of `react-paas-deployer`, 2026-10-10  
**Working product name:** EchoGit (placeholder only; naming is an open decision)  
**Decision requested:** Approve a small technical spike around a self-hosted Forgejo provider, with Django owning tenant policy and PaaS deployment orchestration.

This document intentionally separates a Git repository hosting product from the ability to deploy source from a Git repository. They are related capabilities, but one can be useful without implementing the other.

## 1. Executive recommendation

**Feasible: yes. Build it as a provider-backed Git subsystem, not as a new Git implementation inside Django.**

Recommended first option:

1. Run a self-hosted [Forgejo](https://forgejo.org/docs/latest/) instance as the Git hosting engine. Forgejo owns the Git wire protocols, repository storage, branches/tags/commits, web UI, SSH/HTTPS transport and its provider-side repository API.
2. Add a small Django **Git control-plane wrapper**. It owns PaaS tenant authorization, service/repository bindings, quotas, credentials, deployment intent, webhook verification, audit events and lifecycle coordination. It calls Forgejo through a narrow provider adapter instead of exposing arbitrary Forgejo API access to the browser.
3. Add React screens for repositories and for connecting a repository/ref/subdirectory to a PaaS Service. Link users to Forgejo for repository operations that the PaaS does not implement (file browser, commit history, branch management, pull requests, issues).
4. Keep the existing PaaS deployment engine as the sole execution path. A Git-triggered deployment must resolve a ref to a full commit SHA, fetch source in a restricted worker, create a reproducible source archive, and feed that immutable artifact into the existing `ServiceRevision → Deploy → BuildArtifact/Release → runtime` flow.
5. Start with **manual deploy from a selected commit/ref**. Add verified push-webhook auto-deploy only after the manual path is tested end to end.

Do **not** begin by implementing Git smart HTTP or SSH protocols, merge requests, a new Git object database, a CI runner, and the existing deploy integration all at once. Those are different projects with substantially different operational and security costs.

### Initial recommendation scorecard

| Option | Product fit | Delivery effort | Operational burden | Recommendation |
|---|---|---:|---:|---|
| Forgejo + Django wrapper + React integration | Self-hosted Git product with PaaS-native deploy UX | Medium | Medium | **Preferred spike** |
| Gitea + the same wrapper | Similar provider-backed design | Medium | Medium | Valid alternative; compare release/support and product requirements |
| GitLab CE as the complete Git platform | Broad built-in collaboration and CI features | High | High | Choose only if GitLab-compatible workflow is a firm product requirement |
| Git CLI / bare repositories / `git-http-backend` with a custom Django service | Maximum product control | Very high | High; all protocol and product edges become ours | Not recommended for MVP |
| External GitHub/GitLab/Forgejo providers only | PaaS source deployment without owned repository hosting | Low–medium | Low–medium | Best fallback if hosting repositories is not a hard requirement |

The first decision is a **spike**, not a commitment to the product name or a promise that Forgejo already integrates with the PaaS.

## 2. What the current repositories tell us

This is based on source inspection, not on an assumption that a model choice implies a complete feature.

### Backend: useful foundations already exist

- `src/services/models.py` defines `Service.SourceKind.GIT = "git"`, together with `source_config`, `build_config` and `runtime_config`. This is a useful representation for future source intent, but the enum by itself is not proof of a working Git provider or clone/deploy path.
- `ServiceRevision` already owns immutable executable snapshots, including `source_snapshot`, `build_snapshot` and `artifact_file`. Its save contract prevents changing executable snapshot data after creation. This is the right boundary for pinning a repository/ref/commit and the exact source archive used for a deployment.
- `src/deploy/models.py` contains deployment provenance and artifact/release concepts, including `source_revision`, `BuildArtifact` and `Release`. These should be reused; Git should not introduce a parallel runtime/release engine.
- `src/deploy/apis.py` exposes the existing Deploy create flow with JSON/multipart handling, deployment permission checks and a ZIP upload path.
- `src/deploy/serializers.py` describes `zip_file` as an uploaded deployment ZIP.
- `src/deployments/celery/services/deploy_service.py` extracts the uploaded archive to a temporary directory and runs Docker-source inspection/security validation before the ordinary build path continues.
- `src/services/revisioning.py` materializes service intent into a frozen revision. New source integration should participate before or during this established snapshot boundary, rather than changing mutable Service data while a build is executing.

### Frontend: source deploy is currently ZIP-oriented

- `src/components/service_detail/components/CreateDeployPanel.jsx` currently exposes a ZIP upload workflow, including an “Inspect & suggest config” flow.
- The service detail page already has a Deploy workspace and talks to the Django API. This makes it the natural place for a future “Deploy from Git” source selector.
- The React home-page data contains a Forgejo/Git-hosting entry. That presentation entry must not be taken as evidence that a repository-management API, user identity integration, or Git-to-Deploy pipeline is already implemented.
- In the inspected end-to-end create-deploy path I found no complete, verified flow that authenticates to a Git provider, resolves a ref to a commit, fetches that commit and delivers an immutable source artifact to the normal PaaS deployment engine. Before implementation, run a focused repository-wide code search and trace the actual `SourceKind.GIT` writers/readers so any partial or legacy wiring is not duplicated.

### Feasibility conclusion from these facts

The PaaS already has the durable Service/revision/deploy boundaries needed for integration. The missing product slice is likely the **provider adapter + source-binding API + fetch/snapshot worker + UI**, not a replacement build engine. However, source-kind handling and provider identity/authentication must be traced before writing those components.

## 3. Define which product we are building

“Something like GitLab” can mean several different scopes. These should not be conflated.

### Scope A — Git source deployment only

Users connect a repository from an external or self-hosted provider to a PaaS Service, choose a branch/tag/commit and deploy it. The PaaS owns build/runtime/release behavior. It does not own the repository UI.

### Scope B — Hosted Git repositories integrated with PaaS (recommended first product scope)

Users can create private repositories under their PaaS account, clone/push through normal Git clients, use Forgejo's existing web interface for source-code collaboration, and connect any owned repository to a Service. The PaaS adds an integrated management surface for ownership, quotas, linked services and deploys.

### Scope C — GitLab-like development platform

Build browser-based file editing, diff/commit browsing, branch protection, merge requests, review workflow, issues, package registry, CI runner, artifacts and advanced organization permissions. This is an independent multi-release roadmap, not an MVP requirement.

**Proposed scope:** Scope B, delivered in slices. Scope A remains a valid smaller alternative if hosting repositories is not a must-have. Scope C is explicitly out of initial scope.

## 4. Proposed architecture

```text
Developer's Git client
  | HTTPS / SSH Git protocol
  v
Forgejo (dedicated Git host + repository storage + web UI)
  | signed push webhook
  v
Django Git ingress / control API
  | verify signature, delivery ID, repository binding, branch policy
  | durable event/outbox record
  v
Celery Git-source worker (isolated, bounded workspace)
  | fetch an approved ref
  | resolve and record exact commit SHA
  | validate subdirectory / checkout / archive
  | calculate archive digest and clean up workspace
  v
Immutable source artifact
  | source provenance + SHA-256
  v
Existing ServiceRevision -> Deploy -> BuildArtifact / Release
  -> existing build, rollout, health check, activation and rollback

React PaaS dashboard
  | authenticated API calls
  v
Django Git control API -- narrow provider adapter --> Forgejo REST API
```

### Component ownership

**Forgejo owns:**
- Git object storage and Git over SSH/HTTPS.
- Repository refs, commits, normal Git operations and its repository web UI.
- Provider-native concepts it supports, such as repository collaboration and optional later Actions.
- Provider-side access to Git repositories. The PaaS should not read or mutate Forgejo's internal repository files directly.

**Django wrapper owns:**
- Mapping a PaaS user/workspace to a provider account/repository ID.
- Tenant checks, policy and quota enforcement for PaaS-created repositories.
- Connecting a repository/ref/path to a Service.
- Credential references, webhook registration and verification, replay prevention and audit records.
- Manual deploy requests, automatic-deploy policy and build/deploy status correlation.
- A stable PaaS API independent of the chosen provider. The provider adapter should be replaceable without changing the React contract.

**The existing deployment engine owns:**
- Source policy and validated build inputs.
- Immutable ServiceRevision creation.
- Build resource policy, image/artifact provenance, runtime orchestration, readiness/health, activation, rollback and cleanup.

No Git webhook, Forgejo callback or React request should directly call Docker/Swarm or invent a second deployment state machine.

## 5. Provider choice: Forgejo first, not Gitaly as a standalone engine

### Why Forgejo is the leading candidate

Forgejo is a self-hostable Git collaboration product, rather than just a repository library. Its documentation covers standard Git-client workflows over HTTPS and SSH, a web interface, APIs and repository webhooks. That provides the Git server and much of the user-facing collaboration surface without requiring the PaaS team to implement every Git operation.

Useful starting references:
- [Forgejo documentation](https://forgejo.org/docs/latest/)
- [Forgejo administrator guide](https://forgejo.org/docs/latest/admin/)
- [Forgejo repository and Git-client guide](https://forgejo.org/docs/latest/user/)
- [Forgejo security-related configuration](https://forgejo.org/docs/latest/admin/config-cheat-sheet/)
- [Forgejo deployment recommendations](https://forgejo.org/docs/latest/admin/setup/recommendations/)

Gitea is a valid alternative with similar concepts. Compare the exact version, maintenance policy, API compatibility, backup and migration needs during the spike instead of building a provider-specific API into React.

### Why not use Gitaly directly?

[Gitaly is GitLab's internal repository RPC service](https://docs.gitlab.com/administration/gitaly/), not a complete GitLab-like product API or replacement for a repository hosting UI. GitLab documents it as a service through which GitLab components perform repository operations. GitLab also warns against directly accessing Gitaly-managed repository files because storage layout and correctness depend on the supported interface. A standalone Gitaly integration would leave the PaaS responsible for user-facing hosting, identity, repository lifecycle, protocol ingress and collaboration while adding a GitLab-specific RPC dependency.

If the product requirement is specifically GitLab itself, evaluate GitLab CE as a whole service and its operational footprint. Do not build against its internal storage format or access its repositories directly.

### Why not build the Git protocol ourselves?

Using the Git executable for controlled clone/fetch/archive operations is appropriate. Implementing a custom server for Git's smart HTTP and SSH receive/upload protocol inside Django is different. It introduces protocol correctness, concurrency, authorization on every ref operation, packfile resource limits, large pushes, SSH command restrictions, repository locking and storage-corruption risks. [Git's HTTP protocol documentation](https://git-scm.com/docs/http-protocol) shows that smart HTTP includes specific upload-pack and receive-pack request/response contracts; it is not an ordinary file-upload endpoint.

Only revisit custom Git protocol serving if a future technical spike demonstrates that a provider cannot meet a concrete requirement.

## 6. Recommended MVP boundary

### Include

- One centrally operated Forgejo installation.
- Private repositories by default.
- Repository create/list/detail/rename/archive/delete actions through the PaaS API, subject to explicit ownership rules.
- Clone URL display, branch/ref selection and linked-Service management.
- Manual deploy from a branch, tag or full commit SHA.
- Resolve branches/tags to a full commit SHA before building; store the SHA and source archive digest with deployment provenance.
- A bounded worker that produces an immutable archive and sends it through the current revision/deploy path.
- Owner-scoped audit events, provider errors, rate/size/time limits and safe cleanup.
- Webhook registration and signature verification as groundwork; auto-deploy stays disabled by default until tested.

### Defer

- Browser-based source editor or full code browser.
- Merge requests, advanced review, issue tracker and project boards implemented by the PaaS itself.
- A new CI orchestration/runner subsystem. Optional Forgejo Actions should be assessed separately and must not receive unrestricted Docker-host access.
- Container/package registries, Git LFS, very large monorepo optimization, mirroring/forks and multiple provider types.
- Deployment previews per pull request, promotion workflows and release trains.
- Public repository creation unless an abuse-control and storage policy is approved.
- A custom Git-over-SSH/HTTP server.

## 7. Proposed domain model and invariants

The names below are proposals, not claims that these models already exist.

### `GitProvider` / `GitProviderInstallation`

Represents a configured provider instance.

Suggested fields:
- `id`: UUID.
- `provider_kind`: `forgejo` initially; extensible to `gitea`, `github`, `gitlab`.
- `base_url`: HTTPS API/UI origin; no credentials embedded in the URL.
- `status`: `pending | healthy | degraded | disabled`.
- `capabilities`: server-derived feature flags, not client-controlled permissions.
- `credential_ref`: reference to an encrypted system credential store.
- `created_at`, `updated_at`, `last_health_check_at`.

Do not expose the provider's administrative API token to the browser or keep it in an ordinary Service config/revision snapshot.

### `GitRepositoryBinding`

Maps the repository provider ID to the PaaS owner and repository metadata.

Suggested fields:
- `id`: UUID.
- `owner_user_id`: PaaS owner; later this could become a workspace/team ID.
- `provider_installation_id`: provider instance.
- `provider_repository_id`: stable provider-generated ID (not only a mutable slug).
- `namespace`, `slug`, `display_name`, `description`.
- `visibility`: `private` initially; public only if policy permits.
- `default_branch`, `clone_https_url`, `clone_ssh_url` (URLs must be validated provider output).
- `quota_bytes`, `last_known_size_bytes`, `archived_at`.
- `created_at`, `updated_at`.

Invariant: a client cannot choose or overwrite a provider repository ID, owner ID or clone URL to impersonate another tenant's repository.

### `ServiceGitSource`

Links one PaaS Service to a source and deploy policy.

Suggested fields:
- `id`: UUID.
- `service_id`: FK to an existing Service, unique for the initial single-source-per-Service model.
- `repository_binding_id`: FK to an owned/authorized repository.
- `ref_kind`: `branch | tag | commit`.
- `ref_name`: branch/tag name or requested full commit SHA; validated by provider.
- `subdirectory`: relative build context such as `.` or `apps/api`; no absolute paths or traversal.
- `build_mode`: initially `existing_docker_source_detection`; any later modes must map to currently supported builders.
- `dockerfile_path`: optional relative path under allowed context, only if the selected build mode supports it.
- `auto_deploy_enabled`: false by default.
- `auto_deploy_events`: allowed event kinds, initially push only.
- `auto_deploy_branch_pattern`: explicit branch filter; initially exact branch name.
- `last_requested_commit_sha`, `last_deployed_commit_sha`, `last_event_at`.
- `created_by`, `created_at`, `updated_at`.

The source binding is mutable desired state. Its historical commit/artifact record belongs to an immutable ServiceRevision/deployment provenance snapshot, not to a mutable `last commit` field alone.

### `GitWebhookDelivery` (or equivalent durable inbox/outbox row)

Suggested fields:
- `id`: UUID.
- `provider_installation_id`, `delivery_id` (unique together).
- `repository_provider_id`, `event_type`, `ref_name`, `before_sha`, `after_sha`.
- `signature_verified`, `received_at`, `processed_at`.
- `status`: `received | ignored | queued | processed | failed`.
- `reason`: sanitized failure/ignore reason.
- `deploy_id`: optional linked Deploy.

Invariant: delivery ID idempotency prevents a retry from making duplicate deployments. The delivery is acknowledged only after it has been durably recorded or safely enqueued according to an outbox contract.

### Credential storage

Repository-provider API credentials and webhook secrets need encrypted-at-rest storage, rotation and redaction. Reuse the project's secret-storage approach only if it supports user/provider credentials with correct ownership and rotation semantics; the current Service-scoped secret records should not automatically become a universal credential vault. Git push credentials used by developers must be handled by Forgejo's supported identity/SSH/token system.

## 8. Git-to-deploy lifecycle

1. **Configure:** An owner selects a repository and the permitted branch/tag/commit, plus optional subdirectory/build mode.
2. **Authorize:** Django checks Service ownership, repository ownership/provider membership, plan/policy quotas and that the source binding is permitted for this Service.
3. **Resolve:** The provider/worker resolves the requested ref to an exact full commit SHA. A moving branch name is not a reproducible source identity.
4. **Fetch:** A dedicated worker fetches that exact revision using a provider-scoped credential. Web/API processes do not execute arbitrary clone/build operations.
5. **Validate:** Validate ref format, subdirectory, archive size, file count, paths, symlinks, submodule policy, LFS policy, timeout and disk budget. Never trust filenames or archive entries from a Git tree.
6. **Freeze:** Create a source archive from the selected commit/context, compute SHA-256, and record non-secret provenance: provider/repository ID, ref, full commit SHA, context path, tree/archive digest and source event ID.
7. **Create immutable revision:** Pass the archive and source/build configuration through existing revisioning. Do not mutate an already-created revision when the branch later moves.
8. **Deploy:** Create/run a normal Deploy through the current execution pipeline. Preserve existing plan-based build/runtime limits, Docker-source validation, health checks, runtime ownership fencing, activation and rollback.
9. **Report:** Expose source commit and deployment status in the Service UI and deployment logs. Show useful sanitized errors for missing refs, inaccessible repo, quota, policy rejection, build failure and health failure.
10. **Clean up:** Delete temporary checkout/work directories on success, failure, cancellation and worker restart/recovery. Retain only artifacts according to the defined retention policy.

### Why a pinned commit matters

Suppose the `main` branch receives commit A, then commit B while a deployment is queued. The build must execute one resolved commit and use the exact source archive recorded for that revision. It must not checkout `main` again midway through build or runtime preparation. This is required for auditability, reproducibility and meaningful rollback.

## 9. Proposed PaaS API contract

Routes below are illustrative v1 contracts. They are not implemented endpoints. Prefixes should follow the existing routing conventions after a route review.

| Method and path | Purpose | Important inputs/outputs |
|---|---|---|
| `GET /api/git/v1/providers/` | List enabled provider capabilities for the current user | No credentials in output |
| `GET /api/git/v1/repositories/` | List repositories visible to the current user | `page`, `page_size`, `q`, `visibility` |
| `POST /api/git/v1/repositories/` | Create a repository | `name`, optional `description`, `visibility=private`, `default_branch=main`, optional `initialize_readme` |
| `GET /api/git/v1/repositories/{id}/` | Repository metadata | Provider ID, URLs, default branch, status, size/quota |
| `PATCH /api/git/v1/repositories/{id}/` | Update supported metadata | `name`, `description`, allowed visibility changes |
| `DELETE /api/git/v1/repositories/{id}/` | Delete/unlink a repository | Must require ownership check and explicit confirmation policy |
| `GET /api/git/v1/repositories/{id}/refs/` | List deployable refs | `kind=branch|tag`, pagination, default branch marker |
| `GET /api/git/v1/repositories/{id}/commits/` | List recent commits | `ref`, `limit` with server cap; sanitized commit metadata |
| `GET /api/services/{service_id}/git-source/` | Read source binding | Repo ID, ref policy, subdirectory, auto-deploy state and last deploy SHA |
| `PUT /api/services/{service_id}/git-source/` | Create/update source binding | `repository_id`, `ref_kind`, `ref_name`, `subdirectory`, `build_mode`, optional `dockerfile_path` |
| `DELETE /api/services/{service_id}/git-source/` | Remove Git source binding | Does not delete repository or existing releases |
| `POST /api/services/{service_id}/git-source/deploy/` | Request a manual Git deployment | `ref` or `commit_sha`, optional approved override; returns accepted job/Deploy identity |
| `POST /api/git/v1/webhooks/{binding_token}/` | Provider webhook receiver | Raw body + signature/delivery/event headers; returns quickly after verification and durable enqueue |
| `GET /api/git/v1/deployments/{deploy_id}/source/` | Read source provenance | Resolved SHA, ref, context, archive digest, provider commit URL; never credential data |

### API rules

- Require current session/JWT authentication for user-scoped control APIs and apply the same tenant fencing used by existing service APIs.
- Resolve repository ownership from the database/provider binding. Never trust `owner_user_id` from POST/PATCH payloads.
- Never accept an arbitrary repository URL as permission to clone it. For the MVP, accept a repository binding ID. If external Git URLs are later supported, require an explicit provider/source policy and block SSRF/internal-address/file-protocol abuse.
- Use idempotency keys or unique operation records for manual deploy retries.
- Set explicit request throttles, provider timeouts and pagination caps.
- Do not return access tokens, deploy keys, webhook secrets or credential-bearing clone URLs in ordinary API responses.
- Error responses should use stable machine-readable `code` values plus safe user-facing `detail` strings.

## 10. Webhooks and automatic deploy policy

Forgejo/Gitea-style repository webhooks can deliver push events and support shared-secret signatures. The receiver should verify the raw-body signature before parsing or trusting payload fields. See [Gitea's webhook contract](https://docs.gitea.com/usage/repository/webhooks/) for delivery IDs, event headers, signatures and ref information; confirm the exact header/payload names for the selected Forgejo release during the spike.

### Verification and processing order

1. Enforce HTTPS at the ingress.
2. Match a known binding/installation token and expected provider host.
3. Read the raw request body under a small configured size limit.
4. Validate HMAC-SHA256 using a constant-time compare. Reject missing or invalid signatures.
5. Check provider event type, repository ID, ref and the binding's current branch filter.
6. Deduplicate on provider + delivery ID; store a durable record before returning a successful acknowledgement.
7. Enqueue a worker. The worker re-fetches/validates the repository and resolves the final SHA rather than trusting a payload's URL.
8. Coalesce bursts for the same Service/ref when appropriate. Do not run a second deploy that would race an active operation; use the existing lifecycle/deploy conflict handling.
9. Record ignored reasons as well as successes. Webhook retries must be safe and must not multiply Deploy rows.

### Suggested starting defaults

- Manual deployment: enabled.
- Auto-deploy: disabled until the owner explicitly enables it.
- Auto-deploy ref: one exact branch (default branch shown as a suggestion, not silently assumed).
- Trigger: push event only.
- Deploy latest commit on accepted push after resolving the SHA; ignore tag deletion and unrelated refs.
- A changed source binding or disabled webhook invalidates old queued events for that binding.
- Webhook endpoint secrets are random, rotatable and never shown again after creation.
- No automatic source build for public forks or untrusted pull requests in MVP.

## 11. Security and isolation requirements

Git hosting makes user-controlled repositories executable build inputs. Treat repository content as untrusted.

### Must-have controls

- **Tenant isolation:** every create/read/update/delete, source binding, webhook and repository quota check is scoped to the authenticated owner/workspace. Never trust numeric or UUID IDs without ownership checks.
- **Separate trust boundaries:** Forgejo storage/protocol endpoint, Django control-plane API, and Git/build workers should have separate network and process permissions.
- **No host Docker socket in Git/source workers by default:** source fetching and archive generation should not grant repository code control of the deployment host. The ordinary build runtime can be handled by the existing engine/policy.
- **Credential containment:** use short-lived/revocable tokens where possible; least-privilege provider scopes; redact request headers, credential URLs, environment secrets and raw hook secrets from logs.
- **URL/SSRF defense:** never fetch untrusted remote URLs without allowlisting and resolution checks. Deny `file://`, local socket/file paths, loopback, link-local, private infrastructure addresses and unapproved ports when external providers are eventually permitted. Recheck DNS/IP at connection time to reduce DNS-rebinding risk.
- **Bounded Git processes:** no shell interpolation; pass argument arrays; pinned executable/path; timeout, CPU/memory/process, file-count, checkout-size and disk limits; kill the process group on cancellation.
- **Repository data validation:** enforce safe relative paths, reject path traversal, avoid following symlinks outside the checkout, define a strict submodule allowlist and leave Git LFS disabled until size and credential behavior are specified.
- **No user hooks on the server:** do not execute uploaded Git hooks or accept a config that lets a tenant set arbitrary Git executables/helpers or transport commands.
- **Reproducible source:** pin full commit SHA, record archive digest and relevant build-input/policy version. Never put credentials or secret values into revision snapshots.
- **Webhook security:** HMAC, deduplication, timestamp/replay policy where supported, bounded body, event/ref/repository binding checks, and durable audit.
- **Abuse limits:** repository count, storage, Git push/fetch time, checkout/expanded archive size, manual deployments/day, webhook frequency and build concurrency should be plan- or system-policy-controlled.
- **Backups and deletion:** document repository backups separately from PostgreSQL, restore test cadence, retention for deleted repositories, and orphan recovery between Forgejo metadata and Django bindings.

### Important threat scenarios to test

- An attacker substitutes a repository ID/slug to read another user's private source.
- A webhook is forged, replayed, or delivered twice.
- A branch moves during a queued deployment.
- A submodule points at an internal service or asks to fetch with leaked credentials.
- A crafted tree contains path traversal/symlinks, a huge file, many tiny files or a decompression/checkout bomb.
- A build attempts to exfiltrate a build secret or reach Docker/metadata services.
- A user deletes/revokes the repository while a deploy is queued.
- A push storm or worker crash leaves duplicate Deploys, a stale lock, or temporary source files.
- Forgejo is restored from a backup that is newer/older than the PaaS's repository-binding rows.

## 12. Quota and configuration parameters to decide

These are **proposed knobs**, not existing platform settings or final commercial limits. Put them in a central settings/policy model and document which are plan-specific before implementation.

| Parameter | Suggested initial value/policy | Reason |
|---|---|---|
| `git_hosting.enabled` | false until deployed and health-checked | Feature flag and safe rollout |
| `git_hosting.provider_kind` | `forgejo` | Keep provider-specific behavior behind an adapter |
| `git_hosting.private_by_default` | true | Avoid accidental code exposure |
| `git_hosting.max_repositories_per_user` | 10 (provisional) | Bound initial storage/abuse |
| `git_hosting.repository_soft_quota_mb` | 1024 per repo (provisional) | Initial tenant guardrail; measure actual Git pack/storage behavior |
| `git_hosting.user_storage_quota_mb` | 5120 per user (provisional) | User-level budget in addition to per-repo guard |
| `git_source.max_checkout_bytes` | 512 MiB (provisional) | Limit untrusted working tree size; separate from Git's on-disk repo size |
| `git_source.max_archive_bytes` | 256 MiB (provisional) | Keep build input bounded; adjust to observed apps |
| `git_source.fetch_timeout_seconds` | 120 | Bound stuck/slow Git network operations |
| `git_source.archive_timeout_seconds` | 60 | Bound snapshot preparation |
| `git_source.max_files` | 100,000 (provisional) | Protect CPU/inode usage |
| `git_source.max_concurrent_fetches_per_user` | 2 | Avoid noisy-neighbor source fetches |
| `git_source.max_auto_deploys_per_service_per_hour` | 10 (provisional) | Guard accidental push loops/storms |
| `git_source.submodules_enabled` | false | Avoid indirect network/credential access until designed |
| `git_source.lfs_enabled` | false | Requires separate storage, quotas and fetch policy |
| `git_source.auto_deploy_default` | false | Explicit opt-in avoids surprising production deployments |
| `git_source.allow_external_urls` | false for MVP | Avoid SSRF and arbitrary remote cloning |
| `git_source.branch_delete_policy` | Keep the last successful release; mark binding unresolved and require owner action | Do not delete or auto-select a replacement release |
| `git_source.source_retention_days` | 30 days of unreferenced snapshots, subject to release/rollback retention | Prevent unbounded object/artifact storage |
| `git_hosting.deleted_repo_retention_days` | 7-day soft-delete window (provisional) | Accidental deletion recovery |

All numeric values need a small load/security spike and product/plan review. Do not treat the provisional numbers as approved billable promises. Enforce expanded checkout/archive size separately from compressed Git object storage; they are not the same metric.

### Build strategy choice

The source archive must enter a builder already allowed by the Service plan and existing backend policy. MVP should not introduce a new language/framework entitlement or accept tenant-selected unlimited Docker resources. If the current Docker source detector needs a root-level Dockerfile or another required file layout, the worker must prepare the allowed context accordingly and run the existing validation unchanged.

## 13. React dashboard proposal

### Repository workspace

A top-level **Repositories** dashboard route should provide:
- Repository list/search, namespace/name, private badge, default branch, last update, storage/quota and linked Service count.
- Create repository modal with name, optional README/description, and visibility defaulting to private.
- Clone URLs with copy buttons. SSH URL only if SSH ingress/port and public key/account configuration are correctly set.
- “Open in Forgejo” link for code browsing and collaboration; do not rebuild Forgejo's entire UI in React.
- Clear handling for provider outage, permission denied, quota reached, rename/delete pending and credentials not connected.

### Service → Deploy source

In Service Detail, add a source selector or a dedicated Deploy Source section:
- `ZIP upload` (existing behavior).
- `Git repository` (new).
- Repository dropdown limited to repositories the current user can use.
- Ref kind and searchable branch/tag/commit field; show selected/resolved commit SHA and commit link.
- Optional context/subdirectory; validate it against the repository tree.
- Build mode/Dockerfile path only when the backend supports the requested mode.
- Manual “Deploy this revision” button; separate explicit toggle and confirmation for automatic deployments.
- Source status: connected, last fetched SHA, last successful deployed SHA, last webhook, last deploy result and human-readable failure detail.
- Do not show secret/token values. Use separate status for “source connected” vs “deployment running” vs “runtime healthy”.

On a Git deploy attempt, the UI should show a durable task/deploy ID and then navigate into the existing deployment progress/log experience rather than implementing a second progress UI or state model.

## 14. Delivery plan and acceptance criteria

### Phase 0 — architecture spike (small, required before implementation)

- Deploy a disposable Forgejo instance in a non-production environment.
- Verify provider account/provisioning strategy, API authentication, repo create/delete, normal Git push/clone, webhooks/signatures, backup/restore and repository quota observability.
- Create a temporary repository with a small supported Docker source and run the current PaaS pipeline on a frozen source archive.
- Trace all existing `SourceKind.GIT` call sites and confirm source-binding ownership semantics.
- Decide how PaaS users authenticate to the Git UI and Git over SSH/HTTPS.
- Produce measured resource/security results and refine the proposed defaults.

**Exit gate:** one repository can be created, pushed to, cloned by a restricted worker, pinned to a commit, archived, and deployed through the current engine with no cross-tenant access.

### Phase 1 — manual Git deployment

- Provider adapter and health checks.
- Repository metadata/bindings and owner-scoped API.
- ServiceGitSource API.
- Restricted fetch/archive worker.
- Immutable source provenance connected to ServiceRevision/Deploy.
- React repository picker and manual Deploy source UI.
- Contract tests for ownership, credential redaction, SHA pinning, source cleanup and normal deployment outcomes.

**Exit gate:** a deployment is reproducible from recorded provider repo ID + full commit SHA + source archive digest after the branch moves.

### Phase 2 — push webhook auto-deploy

- Webhook provisioning/rotation UI/API.
- Signature validation, durable delivery inbox, dedup and replay tests.
- Branch filter, concurrency/conflict handling and push-storm coalescing.
- Event/commit correlation on deployment logs and Service overview.
- Disable/revoke behavior and stale queued event handling.

**Exit gate:** duplicate deliveries create no duplicate deploy; invalid signatures never enqueue work; the worker only builds commits accepted by the binding's current policy.

### Phase 3 — broader Git collaboration and integrations

Only after demand is demonstrated:
- Import from external providers and authenticated private external repositories.
- Team/workspace ownership and shared repo permissions.
- Organization/group management and branch protection.
- Optional Forgejo Actions or other CI integration behind isolated runners.
- Git LFS, mirrors, forks, large monorepo optimization and preview deployments.
- Commit status reporting back to provider, release promotion and environment policies.

Do not couple Phase 1 delivery to Phase 3 features.

## 15. Test and operational checklist

### Provider adapter contract

- Create/get/list/rename/archive/delete repo; duplicate slug; provider timeout/rate limit; invalid credential; provider version/capability mismatch.
- Ref listing and exact SHA resolution for empty repo, deleted branch, annotated tag, force-pushed branch, missing commit and repository rename.
- Provider API errors are sanitized; secret values and Authorization headers never appear in API responses or logs.

### Tenant/authorization

- A user cannot list, bind, deploy, rename or delete another owner's repository by changing UUIDs/provider IDs.
- Shared Service permissions do not automatically grant repository administration. Repo access and Service deploy permission are different authority checks.
- Service owner can bind only a repository they own or are explicitly allowed to use.
- Admin/staff status does not bypass tenant fences accidentally.

### Artifact and deployment pipeline

- Commit A is pinned; branch moves to B while the job is queued; build still uses A.
- Archive digest stored and verified; repeated snapshot for the same source inputs gives expected identity.
- Existing Docker-source security inspection still runs; a failed inspection never activates a release.
- Build failure/readiness failure/rollback/cancel/delete all clean up workspaces and preserve existing lifecycle fences.
- Existing archive-based deployments and Ready Apps remain unaffected.
- Git-source deployments obey existing plan/build/runtime and daily deploy limits.

### Webhook

- Invalid/missing signature rejected.
- Unknown repository, ref mismatch, unknown delivery ID, repeated delivery, wrong event type, malformed JSON and oversized body are safely handled.
- Durable acceptance precedes success acknowledgement.
- Repository deletion/revocation while queued cannot make the worker bypass current binding policy.
- A webhook-triggered deployment cannot create an endless push → build → push loop.

### Operations

- Forgejo is backed up with a tested restore; PostgreSQL/metadata backups and repository storage backups are coordinated.
- Repository usage, storage, clone/fetch duration, webhook failures, queue age and source-preparation errors are observable.
- Cleanup reconciles stale checkouts and unreferenced source artifacts.
- Forgejo, Git worker and build runtime have separate network/credential permissions.
- Disaster recovery can reconcile orphaned provider repositories and stale Django mappings.

## 16. Questions that should be answered before coding

The following are open product/operations questions. The suggested choices are defaults for the architecture spike, not decisions silently forced on the product.

| Question | Suggested default for the spike | Why the answer matters |
|---|---|---|
| 1. Do we need Git hosting itself, or only deploy-from-Git? | Git hosting + integrated deploy (Scope B) | Determines whether we operate Forgejo or only integrate providers |
| 2. Must the user see a PaaS-native source browser, or is Forgejo's UI acceptable? | Link to Forgejo; build repo management in PaaS only | Avoid duplicating a large application |
| 3. Should PaaS and Forgejo share one login? | Test linking/provisioning first; don't assume seamless SSO | Affects identity provisioning, SSH keys and support |
| 4. Are repositories personal, group-owned, or both? | Personal ownership in Phase 1; design IDs so workspace support can be added | Defines authorization and quotas |
| 5. Are public repositories allowed? | Private only for MVP | Public hosting needs abuse, moderation and bandwidth controls |
| 6. Should GitHub/GitLab/other external providers be allowed at launch? | No arbitrary URL; one self-hosted provider first | Avoids SSRF and credential explosion |
| 7. Should every push automatically deploy? | No; manual by default, explicit branch-filtered opt-in later | Protects production and prevents deploy storms |
| 8. Which branch is production? | Owner explicitly selects one ref; never assume branch name is `main` | Projects vary and production refs may be protected differently |
| 9. Which project types need to build first? | Only what the current Docker-source validation/build path demonstrably supports | Avoids promising language support not implemented by the builder |
| 10. Do we need CI runners now? | No; use the existing PaaS deployment worker | A runner is another untrusted-code execution platform |
| 11. Can builds access private networks/secrets? | Keep current policy; define build secrets separately before enabling them | Repository code can exfiltrate secrets if egress and mounts are uncontrolled |
| 12. What are the repo/storage/checkout limits and retention? | Use the provisional table above for a spike, then tune from measurement | A Git repository's pack size differs from its checked-out source size |
| 13. Should a deleted repo delete deployed apps? | No. Preserve the last successful release and require an explicit Service action | Source lifecycle and runtime lifecycle must remain separate |
| 14. Do we need per-user SSH keys, HTTPS tokens, deploy keys, or all three? | Verify provider support and choose the smallest supported set | Affects user experience and safe credential revocation |
| 15. What recovery SLA/backups are required? | Write and test a basic backup/restore runbook before production | Git data is customer source code and is not recoverable from a Django DB dump alone |

## 17. Go/no-go decision

**Go for a Phase 0 spike, with Forgejo as the first candidate and the existing PaaS deployment engine retained.** The current model/revision architecture makes integration realistic, while the Git hosting server and source-fetch worker remain new operational/security surfaces.

**Do not yet approve** a custom Git protocol server, GitLab-sized feature parity, arbitrary public Git URL cloning, user build runners with unrestricted Docker access, or automatic deployment on every push. Those choices add risk without being prerequisites for a small useful first release.

The implementation should start only after the Phase 0 exit gate, authentication model and tenant/quota policy are agreed. This document is the design baseline to refine from that spike, not an implementation status report.

## References

- [Current PaaS Service model](../../src/services/models.py)
- [Current Deploy API](../../src/deploy/apis.py)
- [Current Deploy serializer](../../src/deploy/serializers.py)
- [Current DeployService build path](../../src/deployments/celery/services/deploy_service.py)
- [Current immutable revision model](../apps/services/models.md)
- [Current deployment system model](../apps/deployments/execution/01-system-model.md)
- [Forgejo documentation](https://forgejo.org/docs/latest/)
- [Forgejo admin guide](https://forgejo.org/docs/latest/admin/)
- [Forgejo repository guide](https://forgejo.org/docs/latest/user/)
- [Forgejo webhook/config security settings](https://forgejo.org/docs/latest/admin/config-cheat-sheet/)
- [Gitea webhook delivery/signature reference](https://docs.gitea.com/usage/repository/webhooks/)
- [Git Smart HTTP protocol](https://git-scm.com/docs/http-protocol)
- [GitLab Gitaly architecture and storage caveats](https://docs.gitlab.com/administration/gitaly/)
