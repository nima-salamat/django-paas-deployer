# Git Hosting and PaaS Integration — Implementation Gap Analysis

**Status:** Design review and pre-implementation gate; no Git Hosting implementation is claimed here.  
**Reviewed:** 2026-10-10  
**Repositories:** `nima-salamat/django-paas-deployer` (`master`) and `nima-salamat/react-paas-deployer` (`main`).  
**Companion architecture:** [Git Hosting and PaaS Source Deployment — Feasibility and Design Proposal](git-hosting-paas-feasibility.md).

## 1. Executive result

The architecture is plausible, but the prior proposal was not yet a safe implementation contract. Source inspection exposed three confirmed integration gaps and several high-impact decisions that cannot be settled from code inspection alone.

The most important confirmed gap is that the normal Docker-source deployment path still reads `Deploy.zip_file.path` during source inspection. `ensure_revision_for_deploy` also copies an upload into `ServiceRevision.artifact_file`, but that copy does not make the execution path independent of the Deploy ZIP. The previous statement that a frozen revision could be deployed after deleting the legacy Deploy ZIP was therefore too strong. See [GAP-01](#gap-01--revision-artifact-is-not-yet-the-canonical-execution-input).

The next major issue is authority: `Service.source_kind` already allows `git`, and the general Service configuration PATCH accepts `source_kind` and `source_config` for non-catalog Services. A new relational `GitServiceSource` model would be bypassable unless generic write paths are guarded. See [GAP-02](#gap-02--git-source-authority-can-be-bypassed-by-generic-configuration-writes).

The third issue is deployment creation: the existing public create endpoint combines permission checks, daily limits, config normalization and serializer/database behavior. A background source worker cannot safely substitute a call to a DRF ViewSet or create a `Deploy` row on its own. Git hand-off needs one reusable, transaction-aware application service. See [GAP-03](#gap-03--normal-deploy-admission-is-coupled-to-the-http-viewset).

This report distinguishes:

- **Confirmed:** visible in inspected source and should be treated as a required code change.
- **Unverified:** depends on actual infrastructure, version behavior or a technical spike.
- **Decision needed:** product/operations policy that cannot be inferred from the repositories.
- **Deferred:** deliberately outside the manual-deploy MVP.

Do not enable the feature flag or advertise Git in Agent capabilities until all P0 gaps have an accepted resolution and their acceptance tests pass.

## 2. Current-code evidence

The findings are grounded in the following source paths:

| Surface | What the inspected code does today |
|---|---|
| [Service model](../../src/services/models.py#L80-L112) | `Service.SourceKind` includes `git`; source/build/runtime configuration is stored in JSON fields. |
| [Service configuration API](../../src/services/api/configuration.py#L130-L220) | The generic PATCH blocks `source_kind`/`source_config` only for catalog-managed Services; the general path accepts and saves these fields for other Services. |
| [Revision creation](../../src/services/revisioning.py#L720-L895) | `ensure_revision_for_deploy` compiles Service configuration and copies `Deploy.zip_file` into the revision's artifact file. |
| [Deploy create API](../../src/deploy/apis.py#L285-L445) | Permission checks, daily deploy allowance, config/platform normalization and serializer create are joined in the HTTP method. |
| [Deploy serializer](../../src/deploy/serializers.py#L120-L250) | ZIP input, name allocation, Service row locking, validation and Deploy persistence live in the serializer boundary. |
| [Deploy execution](../../src/deployments/celery/services/deploy_service.py#L575-L625) | The non-catalog Docker-source validation path opens `deploy_item.zip_file.path`, extracts the ZIP and inspects that tree. |
| [Agent create-deployment adapter](../../src/agent/application.py#L390-L425) | Git and existing-image inputs are explicitly rejected; archive/ZIP and database-native deployment inputs are allowed. |
| [Agent capability response](../../src/agent/apis/identity.py#L55-L105) | Capabilities advertise `git: false`. |
| [Agent scopes/contracts](../../src/agent/scopes.py), [contract matrix](../../src/agent/contracts.py), [routes](../../src/agent/urls.py) | Agent scopes, route authorization, discovery and generated documentation have separate contract surfaces which must change together. |
| [Top-level routes](../../src/config/urls.py#L12-L38) | Existing API roots are mixed by domain: for example `/services/`, `/deploy/`, `/agent/v1/` and `/api/application-catalog/`. |
| [Compose worker topology](../../compose.yaml) and [Celery settings](../../src/config/settings.py) | The deployment worker consumes `deployments,operations` and has a Docker socket mount; base-image work has its own queue. |
| [React ZIP deployment UI](https://github.com/nima-salamat/react-paas-deployer/blob/main/src/components/service_detail/components/CreateDeployPanel.jsx) | The current deployment creation workspace is ZIP-oriented and provides ZIP inspection/config suggestion. |

These observations do not replace the required exhaustive search of all Git source readers/writers and data inspection for existing Services with `source_kind=git`. Both are Phase 0 tasks.

## 3. Gap register

### GAP-01 — Revision artifact is not yet the canonical execution input

**Severity:** P0 · **Status:** Confirmed

**Evidence:** `ensure_revision_for_deploy` copies `Deploy.zip_file` to `ServiceRevision.artifact_file`, but the ordinary non-catalog Docker inspection path in `DeployService` still reads `deploy_item.zip_file.path`. The fact that a revision-owned copy exists does not mean all execution, rebuild, or source-inspection paths use it.

**Risk:** A revision may appear self-contained in the database while an ordinary deployment still depends on a second ZIP file. Deleting, moving or losing the Deploy ZIP can make a recorded revision non-executable. This also makes source retention and recovery behavior ambiguous.

**Required decision:** Prefer one canonical source-artifact accessor that reads the immutable revision artifact and adapts it to consumers that need a local path. Retain the legacy Deploy ZIP only as an upload/provenance compatibility field, not as the hidden runtime source of truth. If backward compatibility requires retaining Deploy ZIPs for a period, state that as a temporary retention rule rather than claiming independence.

**Acceptance criteria:**
- The execution pipeline, Docker-source inspector, rebuild path and rollback path all obtain source from the same immutable revision artifact contract.
- The storage boundary works with both the current local filesystem and a non-local Django Storage implementation; do not assume every FileField has a usable local `.path`.
- A test creates a revision, verifies its digest, removes or makes the legacy `Deploy.zip_file` unavailable, and proves the revision can still be inspected and deployed through the supported path.
- ZIP-upload deployments and catalog/Ready Apps continue to use their intended immutable inputs and pass regression tests.
- An archive checksum mismatch or missing artifact fails closed before build/activation.

**Do not claim:** bit-for-bit deterministic image builds from a commit SHA alone. This contract gives traceable, immutable source input. Reproducible image bytes additionally depend on base-image digests, package locks, external downloads, builder versions and other build inputs.

### GAP-02 — Git source authority can be bypassed by generic configuration writes

**Severity:** P0 · **Status:** Confirmed

**Evidence:** the general configuration PATCH accepts `source_kind` and `source_config` for non-catalog Services; the allowed enum includes `git`. The Agent configuration API delegates to the general configuration API. This means a future relational source-binding model would not be authoritative unless all generic write surfaces are fenced.

**Risk:** A caller can create an incomplete or forged Git configuration without a valid `GitRepositoryBinding`, bypass repository ownership checks, or leave the relational source and the JSON projection inconsistent. Agent and browser behavior could differ.

**Required resolution:**
1. Add one Git-source application service as the only writer of `GitServiceSource` and the derived `Service.source_config` projection.
2. Reject generic PATCH attempts to set `source_kind=git`, mutate the Git projection, or clear a valid Git binding outside that service. Generic reads may expose a sanitized normalized projection.
3. Audit all write paths, including Service serializers/viewsets, configuration APIs, Agent routes, admin operations, management commands and background tasks—not only the one PATCH endpoint.
4. Preserve existing catalog ownership restrictions and avoid weakening them while introducing Git guards.
5. Before migration, inspect actual database rows with `source_kind=git`; classify and report them instead of silently treating arbitrary JSON as a valid binding.

**Acceptance criteria:** browser API, generic Service serializer, Agent configuration PATCH and any other discovered writer all reject a fake repository UUID, a cross-tenant binding and direct mutation of the Git projection; only the Git-source application service can perform an authorized atomic update.

### GAP-03 — Normal Deploy admission is coupled to the HTTP ViewSet

**Severity:** P0 · **Status:** Confirmed

**Evidence:** `DeployViewSet.create` includes Service existence, owner/share permission, daily deploy allowance, source/platform config normalization, DB validation and serializer persistence. The serializer separately applies permission checks, locks the Service while allocating a name and saves the Deploy.

**Risk:** A source worker that fabricates a request or directly calls `Deploy.objects.create` can bypass one of these checks, count the same request twice, or drift from future changes to the normal deployment contract. A DRF ViewSet is not a stable internal domain-service boundary.

**Required resolution:** Extract/reuse an application-level Deploy admission service that can be called by the HTTP API and GitSourceOperation hand-off. It must take an authenticated actor/request context, Service, trusted source artifact and server-owned provenance; evaluate `can_deploy_add`, plan/policy, daily quota and name/idempotency rules; then create one normal Deploy inside a transaction. The HTTP layer should translate the result into HTTP, not own the business workflow.

**Acceptance criteria:**
- The Git worker never constructs a DRF request or calls a ViewSet method.
- Existing ZIP/API/Agent creation behavior remains equivalent under regression tests.
- Authorization and the daily deployment allowance are enforced exactly once per accepted Deploy.
- A repeated manual request or duplicate worker delivery finds the existing GitSourceOperation/Deploy and cannot create another attempt.
- Provider/source fetch failure before Deploy hand-off does not consume a Deploy slot; quota semantics for a successful hand-off are explicit.

### GAP-04 — Provider identity and the least-privilege fetch credential are not decided

**Severity:** P0 · **Status:** Unverified / decision needed

**Unknowns:**
- Is each PaaS user provisioned as a Forgejo account, is each PaaS tenant represented by an organization, or are repositories owned by a limited service account?
- Which identity authenticates Git push over HTTPS and SSH, and how are SSH keys, token rotation, account suspension and account deletion handled?
- How can the source worker fetch one private repository without receiving an instance-wide administrator token?
- Who provisions and rotates per-repository fetch credentials, and how are they revoked after a repository is disconnected/deleted?

Forgejo documents that access tokens can be scoped to specific repositories, and those tokens have more restrictive route scopes; this is a candidate to test, not proof that the desired provisioning workflow is already possible. See [Forgejo access-token scope](https://forgejo.org/docs/v17.0/user/authentication/token-scope/).

**Recommended spike candidates, in order:**
1. A per-repository read-only SSH deploy key managed by the provider adapter.
2. A per-repository access token with read-only repository scope, if it can be provisioned, rotated and revoked reliably.
3. A dedicated restricted bot identity only if repository-level access controls cannot satisfy the contract.

The operator/admin credential may provision repositories and keys, but it must never be copied into the Git worker environment. The worker receives only a repository-scoped credential. Test both a successful fetch and a negative fetch against another tenant's private repository.

**Acceptance criteria:** the team can demonstrate the complete lifecycle—provision, read-only fetch, revoke, fetch denied after revoke—without using a cross-tenant administrator credential in the worker.

### GAP-05 — Worker isolation requires more than adding a new Celery queue

**Severity:** P0 · **Status:** Confirmed design requirement; deployment-specific details unverified

The current deployment worker mounts `/var/run/docker.sock` and consumes `deployments,operations`. Git preparation executes no project build commands by design, so it should not run on that worker. A new queue alone is insufficient if the generic worker also consumes it or the service has the same host mounts.

**Required resolution:**
- A dedicated `git-source` queue and Compose service consuming only that queue.
- No Docker socket, Docker host-root mount, privileged mode or runtime shell access for the source worker.
- Dedicated non-root process identity, isolated temporary workspace, restrictive filesystem permissions, process-group cancellation and bounded CPU/memory/disk/time/file counts.
- A restricted Git execution environment: absolute executable, argument arrays, noninteractive mode, isolated HOME/config, no inherited credential helpers or URL rewrites, no user-provided Git executable/filter/hook behavior.
- Network egress rules that permit only required control-plane infrastructure and the configured Git provider/approved credential endpoint. A Docker network declaration is not itself an egress firewall; document and test the actual network/firewall policy.
- Worker outputs are data artifacts only. Project code is not executed until the existing, policy-controlled build pipeline takes over.

**Acceptance criteria:** configuration tests prove the source queue is consumed by exactly the isolated worker; container inspection proves no Docker socket/host-root mount; network tests show the worker cannot reach unapproved hosts; killing a worker leaves no active Git process or leaked credential.

### GAP-06 — Cross-worker artifact storage is not a portable contract yet

**Severity:** P0 · **Status:** Unverified

Django's default `MEDIA_ROOT` is filesystem-backed, and the current Compose setup bind-mounts the project tree into several services. That can make paths visible in a single-host development/deployment layout, but does not establish a portable contract for separate hosts, future worker scaling, object storage or restore. Some current execution code relies on `.path`, which many storage backends do not provide.

**Required resolution:**
- Define source artifact persistence in terms of the Django Storage API or an explicit artifact-storage port (`save/open/exists/delete`), not as a local path stored in the operation row.
- Decide whether Phase 1 requires one-node shared storage or supports multi-node execution. State that limit honestly.
- Verify that the API process, source worker and deployment worker all read the same exact archive bytes and digest.
- Make the hand-off atomic from the business perspective: persist complete archive, verify digest, commit operation metadata, then permit Deploy creation.
- Include staged artifact and revision artifact in backup, cleanup, quota and retention policies.

**Acceptance criteria:** an archive prepared by one worker process can be consumed by another process (and, if supported, another node); worker restart and storage errors cannot create a partial archive treated as valid source.

### GAP-07 — Context-directory and archive layout semantics are not proven

**Severity:** P0 for any non-root context; **Status:** Unverified

The existing Docker-source path inspects the uploaded ZIP tree and expects the source layout that the current detector/builder supports. The Git design allows a `context_path` and optional `dockerfile_path`, but does not yet specify a tested archive transformation that puts the selected subtree at the expected archive root. Blindly archiving a path from a Git tree can preserve that path as a leading directory; the existing inspector may then not find a root-level Dockerfile.

**Required resolution:**
- Choose the archive algorithm and prove its path semantics against the pinned tree.
- Either support root context only in Phase 1 or implement a safe copy/repack step that places only the selected context at archive root.
- Validate the resulting ZIP with current archive/path protections and the existing Docker-source security inspection; Git-origin does not mean trusted-origin.
- Defer custom Dockerfile paths until the existing inspector and build contract explicitly support them.
- Keep submodules and LFS disabled until their network, credentials, tree size and archive behavior are designed.

**Acceptance fixtures:** root Dockerfile; application under a subdirectory; monorepo where only one subdirectory is deployed; absent Dockerfile; symlinks; Git submodule entries; huge tree/file; unsafe or unsupported entries; commit with deleted/renamed context directory. The expected result for each fixture must be stated before implementation.

### GAP-08 — Git-supported builder matrix is undefined

**Severity:** P0 for the Phase 1 platform scope; **Status:** Unverified

The current pipeline uses the Service plan to select the execution family and uses ZIP source in several build paths. The proposal mostly describes the Docker-source detection path; it should not silently imply every current plan/framework can build from Git on day one.

**Required resolution:** create a matrix listing each Service plan platform/source mode, required root files, supported build context and whether Git archive input is safe in the existing builder. Phase 1 should support only rows proven in end-to-end tests. Unsupported combinations must fail during source binding or preflight with a stable explanation—before consuming a build slot.

**Acceptance criteria:** each enabled platform has at least one end-to-end Git-to-runtime fixture and one negative unsupported-layout fixture; all existing ZIP and Ready Apps regression tests remain green.

### GAP-09 — Proposed repository quotas are not yet enforceable product limits

**Severity:** P1 before public launch; **Status:** The old per-repository assumption is unverified

The previous design listed a `repository_soft_quota_mb` per repository. Do not publish that as a hard or billable per-repository limit until it is proven. Forgejo's current soft-quota documentation describes a quota feature that is disabled by default, is still in development, and may permit an in-progress operation to finish above the limit. Its documented repository subject is aggregate `size:repos:all`; fine-grained public/private repository subjects are marked not yet available in the configuration reference. See [Forgejo soft quota and its limitations](https://forgejo.org/docs/v17.0/admin/advanced/quota/) and the [quota subject reference](https://forgejo.org/docs/latest/admin/config-cheat-sheet/).

**Required resolution:**
- Prove which limit can be enforced per Forgejo user/group and how quickly usage updates after a push.
- Separate Git object storage, LFS, package/attachment storage, checkout size, prepared archive size and build cache. They consume different resources.
- Choose whether the first release promises per-user/group quota only or builds a separately measured per-repository policy.
- Define behavior on quota exhaustion: reject a new repository, prevent additional pushes when supported, reject fetch/archive, or merely warn. Do not present a warning as enforcement.
- Make provisional limits operator-controlled and clearly labelled until measured.

**Acceptance criteria:** automated tests or a repeatable provider-level experiment shows a push crossing/meeting each claimed limit, the exact enforcement outcome, its delay and its effect on other repositories belonging to the same tenant.

### GAP-10 — Webhook authenticity and durable dispatch need version-specific validation

**Severity:** P1 for manual-deploy MVP; P0 before auto-deploy; **Status:** Unverified

The proposal correctly calls for signature verification and deduplication, but the exact Forgejo version's header names, signature format, delivery identifier and retry behavior must be confirmed. A generic Gitea webhook reference is not proof of identical behavior in every Forgejo release.

**Required resolution:**
- Pin the Forgejo version in the spike and record real example requests for push, branch deletion and force-push.
- Verify HMAC against the raw request body using constant-time comparison; enforce a maximum request size and strict content type.
- Bind the hook to a known installation and repository ID; never trust payload-supplied clone URLs or use them to choose an outbound host.
- Store a unique provider + delivery ID inbox row before successful acknowledgement.
- Ensure committed-but-undispatched rows are recovered after broker/send failure. Celery retry/redelivery semantics alone are not the source of truth: use DB state, operation idempotency and a reconciliation task.
- Specify what happens for force-pushes, tag events, deleted refs, multiple Services linked to one repository and push bursts. Coalescing must not start two conflicting Deploys for a Service.
- Restrict Forgejo's webhook egress to the exact public PaaS ingress host; do not solve an allowlist error by allowing every private address or using `*`.

**Acceptance criteria:** duplicate valid webhook creates one operation; invalid/missing signatures never enqueue; oversized/malformed payloads are rejected; task publish failure recovers; a deleted/revoked binding cannot trigger a new Deploy.

### GAP-11 — Agent support spans several contracts and is not one endpoint

**Severity:** P1 for Agent users; **Status:** Confirmed

Git is currently explicitly unsupported in Agent create-deployment and capability output. When it is implemented, registering a new URL alone is incomplete.

**Required resolution:** update these surfaces together:
- `src/agent/scopes.py`: known scopes, categories, labels and high-risk scopes;
- `src/agent/contracts.py`: route method/path/scopes/idempotency/throttle metadata;
- `src/agent/urls.py` and a thin Git Agent API adapter;
- `src/agent/apis/identity.py`: capability projection;
- `src/agent/apis/deployments.py`: help input contract;
- `src/agent/skills.py` and generated `AGENT.md`/OpenAPI;
- Agent scope management and contract tests in the UI/administration surface.
- Agent authorization remains Agent scope AND the underlying PaaS user's permission AND relevant ServiceShare action permission. Repository administration requires repository ownership independently.
- Never grant new Git scopes implicitly to existing Agent credentials.

Use a dedicated Git source-operation endpoint. The general `POST /agent/v1/deployments` must continue rejecting `source=git` so callers cannot skip repository binding and provenance checks.

**Missing API behavior to specify:** provide a source-operation cancellation endpoint. Before hand-off it cancels the fetch operation under the operation lease; after hand-off it must delegate to the normal Deploy cancellation contract and re-check the caller's `deployments.cancel` permission. Do not implement a second runtime cancellation system.

### GAP-12 — Proposed browser API paths do not yet follow one explicit route contract

**Severity:** P1; **Status:** Confirmed documentation ambiguity

The earlier proposal mixes `/api/services/{id}/git-source/` with a new `/api/git/v1/` prefix, while current top-level paths include `/services/`, `/deploy/`, `/api/application-catalog/` and `/agent/v1/`.

**Recommended decision:** put the browser Git API under one versioned root such as `/api/git/v1/`, and keep Agent endpoints under `/agent/v1/`. Put Service source-binding routes under the Git root (for example `/api/git/v1/services/{service_id}/source`) so repository, binding, operation and webhook contracts have a stable owner and version. Treat every route in the prior document as illustrative until this choice is accepted. Do not add two aliases for the same mutation unless there is a documented migration need.

**Acceptance criteria:** one route table is the source for Django URL registration, OpenAPI/schema docs, frontend API client, Agent contracts and tests.

### GAP-13 — Repository hosting topology and public Git access are not specified enough

**Severity:** P0 for launch; **Status:** Decision needed

The current PaaS ingress is centered on HTTP(S); adding Git Hosting also requires a stable provider hostname, canonical clone URLs and an actual SSH/HTTPS Git transport contract.

**Required decisions and tests:**
- Use a dedicated Git origin (for example, `git.<domain>`) rather than a user-controlled same-origin subpath. Forgejo documents same-origin browser security risks for subpath hosting; see [Forgejo reverse-proxy guidance](https://forgejo.org/docs/v17.0/admin/setup/reverse-proxy/).
- Decide whether SSH clone/push is enabled at launch. If enabled, choose the external SSH host/port and ingress/firewall forwarding; do not assume the PaaS HTTP reverse proxy exposes Git SSH automatically.
- Separate user-facing clone URL generation from the worker's trusted provider endpoint if internal routing is required. The worker must not use arbitrary client- or payload-supplied URLs.
- Disable public self-registration and custom Git hooks unless a separate abuse/security review approves them. Forgejo warns that custom hooks can execute arbitrary commands on its host; see the [configuration reference](https://forgejo.org/docs/latest/admin/config-cheat-sheet/).
- Verify canonical `ROOT_URL`, reverse-proxy trust, TLS validation, request body/push size, large push timeout and repo backup layout with the pinned provider version.

**Acceptance criteria:** a new developer can create/clone/push a private repo using every transport advertised by the PaaS; an unrelated unauthenticated client cannot read or write it; the source worker can fetch via its separate least-privilege route.

### GAP-14 — Source deletion, operation cancellation and recovery semantics are incomplete

**Severity:** P1; **Status:** Design needs completion

The proposal states that deleting a repository should preserve the last successful runtime, but that policy needs concrete transitions and races defined.

**Required contract:**
- Repository delete is a tombstone/delete workflow, not an immediate DB cascade while a source binding, queued operation or webhook references it.
- Disconnecting a binding increments its generation, prevents new operations and invalidates queued work. Physical binding deletion occurs only after references are detached and retention permits it.
- A source operation snapshots Service ID, repository ID and source-generation; deleting the live FK must not erase audit history. Use nullable relations plus immutable identifier snapshots where retention requires it.
- Define whether repository deletion is blocked while another Service uses it, whether it force-disconnects bindings, and how the user confirms the effect.
- If the branch/ref disappears, fail with a stable source error; never select another branch automatically.
- If a repository is revoked after a source archive has been prepared but before Deploy dispatch, the final authority check rejects the dispatch. If already dispatched, existing Deploy lifecycle governs runtime; repository deletion must not silently delete the working Release.
- Document cleanup retention for temp checkouts, staged archives, immutable revision artifacts and Deploy ZIP compatibility files separately.

**Acceptance criteria:** deletion/revocation races are tested against both queued and running source operations; last known successful runtime and revision remain available subject to normal platform retention.

### GAP-15 — Service concurrency, idempotency and auto-deploy policy need a single definition

**Severity:** P1; **Status:** Decision needed

A durable GitSourceOperation status is allowed to cover only source preparation/dispatch. The existing Deploy lifecycle owns build, runtime, readiness, activation, rollback and cancellation. The hand-off nevertheless creates race windows.

**Required resolution:**
- Use a DB-enforced unique relationship from one source operation to no more than one Deploy. A check-then-insert without a unique constraint is insufficient under concurrency.
- Use a monotonic source generation plus attempt/lease fencing. Celery task ID and Redis state are correlation/coordination—not sufficient mutation authority.
- Before a job commits an archive or dispatches Deploy, re-check source generation, repository status, Service existence, cancellation and policy under a transaction/lock appropriate to the operation.
- Define the manual branch semantics: resolve branch once when accepted or when the worker begins? Recommended default: create durable intent immediately, resolve once when the worker begins, persist SHA before fetch; after that, retry the same SHA only.
- For webhook pushes, decide whether to deploy every accepted commit or coalesce unstarted pushes and deploy the newest accepted commit. Recommended default: coalesce only queued/unstarted requests for the same Service/ref; never silently change an already pinned operation and never run two Deploys concurrently for one Service.
- Define source-operation cancellation as its own pre-dispatch transition; after hand-off use the existing deployment cancellation endpoint/state machine.

**Acceptance criteria:** concurrent duplicate manual requests, webhook duplicates, push storms, source-config edits, branch force-push, cancellation and worker lease loss all produce one deterministic outcome with no stale activation.

### GAP-16 — Build-time secrets, egress and untrusted source policy are not explicitly gated

**Severity:** P0 if Git sources can reach protected credentials; otherwise P1; **Status:** Security review needed

Git source is untrusted input, just like an uploaded ZIP. A Dockerfile or dependency build can execute repository-controlled commands once it reaches the existing build engine. Keeping Git fetch isolated does not itself prevent build-time data exfiltration.

**Required resolution:**
- Phase 1 uses only the existing build/runtime policy, never a new unrestricted runner.
- Inventory current build-time environment variables, build args, cache behavior, network access, mount permissions and secret handling before enabling private-repo deployments.
- Provider fetch credentials must never appear in Deploy.config, Service config snapshots, environment snapshots, build args, image layers, logs or the archive.
- Define build secrets separately from Git credentials. Do not pass secrets as ordinary Docker build args. If a safe BuildKit secret contract is not present/verified, do not expose new build secrets in Git MVP.
- Define whether tenant build steps can reach private service networks, cloud metadata endpoints, provider APIs or platform control-plane networks; restrict egress where possible.
- Preserve existing Docker-source inspection, archive-path protections and platform/plan enforcement. A valid commit is not a trusted Dockerfile.

**Acceptance criteria:** a malicious fixture attempting to read provider credentials, access host control-plane endpoints or embed secret-bearing values into source/archive/build output cannot obtain them; normal ZIP and Ready Apps controls still pass.

### GAP-17 — Database migration and compatibility audit are not optional

**Severity:** P0; **Status:** Not yet run

A code enum can exist for a long time before the feature is implemented. It is not safe to assume the database has no rows with `source_kind=git`, nor safe to reinterpret unknown legacy JSON during deployment.

**Required resolution:**
- Run a read-only audit query/report for every Service where `source_kind='git'`, capturing service owner, source_config keys (not secret values), status and revision references.
- Search all code for writes/reads of `source_kind`, `source_config`, `artifact_file` and `zip_file`; review model serializers, catalog paths, deployment helpers and rollback code.
- Decide each legacy row's disposition: migrate to GitServiceSource after validating ownership/provider mapping; mark invalid and require owner repair; or leave unchanged without enabling Git behavior.
- Add DB migrations with unique/FK constraints and a reversible/quarantine strategy. Do not make migration success depend on live Forgejo API calls inside a database schema migration.
- Make the feature flag default false until the data audit and repair path are documented.

**Acceptance criteria:** migration dry-run reports counts and sample IDs without exposing credentials; zero invalid records are silently activated; reverse/repair instructions exist.

### GAP-18 — Backup, restore and incident response require provider-aware contracts

**Severity:** P1 before external launch; **Status:** Not verified

A Django database dump alone cannot recover Git repositories. A repository restore can also diverge from binding, webhook and operation records.

**Required resolution:**
- Back up Forgejo's database, Git repository storage, LFS data if later enabled, attachments/assets that are in scope, config and encryption/credential keys according to provider guidance.
- Test restore to an isolated hostname/database and reconcile stable provider IDs with Django bindings. Record how webhook secrets/credentials are rotated after restore.
- Define user-facing delete/restore retention, incident access audit, source-artifact retention and privacy requirements for private code.
- Add health/readiness for the provider and distinguish provider outage from deployment/build failure.
- Define failure messaging for provider API outage, Git transport outage, exhausted quota, inaccessible repository, missing object, and cleanup debt.

**Acceptance criteria:** a written restore drill can recover a private repository and its authorized source binding without opening cross-tenant access or accidentally deploying a different commit.

### GAP-19 — Metrics, operational limits and support ownership are not assigned

**Severity:** P1 before public launch; **Status:** Unverified

The proposal has provisional byte/time/queue values but does not yet say which subsystem actually measures and enforces each one.

**Required resolution:** make an ownership table for repository count, tenant repository storage, checkout expanded bytes, archive bytes, file count, per-user concurrent source fetches, provider API rate limits, Git worker timeouts, queued operations, webhook retry age, retained artifacts and deploy/day limits. Each entry must identify:
- authoritative measurement source;
- enforcement point (provider, Django admission, worker or deployment policy);
- failure code and user-visible behavior;
- metric/alert and operator action;
- retention/cleanup owner.

Do not advertise a quota in the UI if no code path enforces it. Do not use Celery result state as the only operational record.

### GAP-20 — Frontend route, authorization and source UX contract is not designed to completion

**Severity:** P2 for backend spike, P1 for beta; **Status:** Incomplete

The current React workspace creates Deploys by ZIP. The proposal identifies a repository workspace and Git source selector but needs a field-level UI/API contract.

**Required resolution:**
- Decide whether the user navigates to Forgejo for full repository operations; avoid reproducing repository browser, commit diff, pull requests or issues during the MVP.
- Specify create-repository empty/default initialization behavior; initialize README only on explicit request because it can create an unrelated first commit for users pushing an existing local history.
- Define UI states separately: provider unavailable, no repository, repository permission failure, source disconnected, ref missing, preparing, prepared, dispatched, Deploy running, Deploy failed, runtime unhealthy and last successful revision preserved.
- Refuse source-binding writes for shared-Service collaborators in MVP; repository administration and Service deployment authorization are separate.
- Show commit, source archive digest, context directory, trigger type and associated Deploy. Never show tokens or webhook secrets.
- If auto-deploy is added later, display the exact accepted branch and explain production consequences; default off.

**Acceptance criteria:** the user can trace each Git source operation to the normal Deploy details/log page, and the UI never treats a queued operation as a successful deployment.

## 4. Product and architecture decisions to settle

These questions should become explicit recorded decisions before Phase 1. Suggested defaults are not final product promises.

| Decision | Recommended MVP default | Why it must be recorded |
|---|---|---|
| Product scope | Forgejo-hosted private repositories plus manual deploy from Git | Distinguishes hosting from external-provider integration and full GitLab feature parity |
| Tenant identity | Decide between personal provider accounts and PaaS-managed org/namespace during Phase 0; do not assume SSO | Controls repository ownership, token scope and user offboarding |
| Git transports | HTTPS initially, SSH only if host/port/keys are proven; no transport should be advertised until tested | Current PaaS HTTP ingress does not automatically prove Git SSH is configured |
| Provider support | One pinned Forgejo release behind an adapter | Avoids premature generic-provider behavior |
| External URLs | No arbitrary Git URL clone; only an owned binding | Avoids SSRF and uncontrolled credentials |
| Source mode | Only builder/platform combinations verified in the Phase 0 matrix | Prevents the product promising unsupported frameworks |
| Context path | Root context first if subdirectory root-repacking is not proven | Reduces archive/build ambiguity |
| Submodules / Git LFS | Disabled for MVP | Separate remote-fetch, credential and storage policies required |
| Manual ref semantics | Resolve once when worker starts, persist SHA, retry same SHA | Predictable operator/user intent |
| Auto-deploy | Disabled until Phase 2; one exact branch + push event | Keeps production deployment opt-in |
| Push storms | Coalesce only unstarted operations; never mutate an already pinned operation | Prevents two builds racing or a silent commit switch |
| Ownership | User-owned repos; repository/source binding writes owner-only | Team/org ownership and delegated repo access need a separate policy |
| Quotas | Hard enforcement only where provider/platform can prove it; provisional values hidden | Avoids unenforced commercial promises |
| Artifact retention | Preserve every revision artifact required by rollback policy; clean only unreferenced staging data | Source lifecycle must not break runtime recovery |
| Restore target | Agree RPO/RTO and conduct a provider-plus-control-plane restore drill | Git hosting adds a separate durability boundary |

## 5. Phase 0 — evidence-producing spike

The spike should result in artifacts and logs that prove the design, not only a working demo.

### A. Provider and identity

- Deploy the chosen Forgejo release at a dedicated HTTPS hostname with canonical `ROOT_URL`; verify external clone URLs and any planned SSH host/port.
- Disable public registration and custom hooks unless a reviewed exception is recorded.
- Provision one owner and one private repository. Push from a normal developer client over every advertised transport.
- Prove per-repository read-only fetch credentials, rotation and revocation. Include a negative test against another private repository.
- Exercise repository create, rename, archive, delete/tombstone, branch/tag enumeration, commit resolution and provider timeout/error mapping.
- Capture provider version, configuration diff, credential scope and backup/restore instructions.

### B. Archive and execution path

- Use one small supported Docker project at repo root and another nested in a monorepo.
- Resolve a branch to commit A, move the branch to B after pinning, then prove the resulting archive and Deploy still use A.
- Verify context-path repacking, root-level detector inputs, ZIP validation, symlink handling, file counts and expanded byte caps.
- Compare SHA-256 at archive output, staged storage, Deploy hand-off and revision-owned artifact.
- Remove the legacy Deploy ZIP after revision persistence and prove the canonical source artifact path still works before approving the promised retention model.
- Deploy through the existing build, runtime, readiness, activation and rollback path—not a custom Git-specific runtime path.
- Run one successful, one deterministic validation failure, one transient provider failure, one cancel-before-dispatch and one revoke-during-preparation scenario.

### C. Control-plane, permissions and idempotency

- Test Service owner, permitted shared-service deployer and unrelated tenant.
- Try to forge `source_kind=git` and `repository_binding_id` through all generic browser/Agent write paths.
- Verify a GitSourceOperation uses the same Deploy admission and daily limit as ZIP deploys, exactly once.
- Send the same Idempotency-Key twice and deliver the same webhook twice; show one operation and at most one Deploy.
- Kill/restart the source worker during checkout, after archive write, and after Deploy creation but before marking hand-off complete. Verify DB reconciliation repairs state.
- Prove source-worker queue separation and that the container has no Docker socket/host-root mount or unapproved egress.

### D. Agent contract

- With a current Agent that has no Git scopes, verify it cannot access Git operations and the existing `git=false` capability is unchanged.
- After enabling Git only in a test build, verify scopes, route contract, capability response, OpenAPI, `AGENT.md`, skills, error codes and idempotency descriptions agree.
- Verify HTTP `202` means accepted/preparing only. Agent must inspect source-operation state and the linked normal Deploy terminal state before reporting success.

### E. Webhook and quotas (only if Phase 2 is attempted in the spike)

- Capture real signed requests for push, force-push and branch deletion from the pinned Forgejo version.
- Test bad signature, changed body, missing delivery ID, duplicate ID, oversized body, wrong repo, disabled binding and source generation changed during queueing.
- Test configured egress restrictions and provider hook allowlist without permitting arbitrary private-network destinations.
- Measure repository size/quota updates under a push; document any overshoot or delay. Decide whether the platform enforces per-repo, per-user/group or only warning thresholds.

## 6. Required tests before changing the current Git capability flag

| Contract | Minimum must-pass regression |
|---|---|
| Source artifact | revision deploy/rebuild/rollback path remains functional without needing mutable branch resolution or the legacy upload ZIP |
| Source authority | generic Service PATCH and Agent config cannot bypass GitServiceSource validation |
| Cross-tenant | owner A cannot enumerate, bind, fetch, rename or delete owner B's private repository |
| Credential handling | repository fetch credential cannot read unrelated repositories and is never logged or snapshotted |
| Ref pinning | a branch moving A → B does not change an operation already pinned to A |
| Operation/Deploy hand-off | one source operation is linked to no more than one normal Deploy under concurrent retries |
| Admission/quota | user/share permission and daily Deploy allowance are applied exactly once |
| Storage | source archive is complete and digest-verified across all processes that consume it |
| Queue isolation | git-source worker is the only consumer of the source queue and has no Docker host access |
| Cancellation/revocation | worker losing its lease or source authority cannot publish an archive or dispatch Deploy |
| Existing features | ZIP deploy, database-native deploy, Ready Apps, standard rollback and reconciliation regression tests pass |
| Agent | scopes, OpenAPI, capability, skill and runtime authorization remain aligned |
| Webhook (Phase 2) | forged/replayed/duplicated or stale events never create extra Deploys |
| Recovery | worker/process/broker interruption can be repaired from durable DB state without stale activation |

## 7. Exit gates and decision

### Gate 0 — before schema implementation

Must have:
- Recorded owner/namespace/authentication model.
- Proven read-only worker credential and public Git transport path.
- Source/platform/context compatibility matrix.
- An agreed canonical artifact storage path and explicit fix for GAP-01.
- A safe plan for generic configuration guards, model migration and internal Deploy admission.
- A stated quota/retention policy that does not promise unsupported enforcement.

### Gate 1 — before manual Git beta

Must have:
- P0 gaps resolved with passing end-to-end tests.
- The source archive/commit provenance survives branch movement, restart and repository rename/deletion.
- All Git operation and Deploy transitions are visible and auditable.
- Existing Deploy lifecycle remains the sole runtime authority.
- Operator restore and cleanup runbooks documented.

### Gate 2 — before enabling auto-deploy

Must additionally have:
- Version-specific webhook signature/delivery contract verified.
- Durable inbox/reconciliation and duplicate handling tested.
- Exact branch policy, conflict/push-storm behavior and cancellation semantics defined.
- Provider webhook egress allowlist, rotation and revocation implemented.
- Auto-deploy off by default with explicit owner opt-in and visible current policy.

**Recommendation:** proceed with Phase 0 only. Do not implement repository CRUD and React screens ahead of the source-artifact hand-off, provider credential model, generic-write guard and Deploy admission boundary. Those choices decide whether the resulting feature integrates with the existing platform safely or creates a parallel, weakly fenced pipeline.

## 8. References

### PaaS source of truth
- [Service model](../../src/services/models.py)
- [Service configuration API](../../src/services/api/configuration.py)
- [Revision creation](../../src/services/revisioning.py)
- [Deploy API](../../src/deploy/apis.py)
- [Deploy serializer](../../src/deploy/serializers.py)
- [DeployService](../../src/deployments/celery/services/deploy_service.py)
- [Agent application adapter](../../src/agent/application.py)
- [Agent scopes](../../src/agent/scopes.py)
- [Agent endpoint contracts](../../src/agent/contracts.py)
- [Agent capability response](../../src/agent/apis/identity.py)
- [Top-level URL configuration](../../src/config/urls.py)
- [Compose worker topology](../../compose.yaml)

### External contracts to verify against the pinned versions
- [Forgejo access token scopes and repository-specific tokens](https://forgejo.org/docs/v17.0/user/authentication/token-scope/)
- [Forgejo soft quota and its limitations](https://forgejo.org/docs/v17.0/admin/advanced/quota/)
- [Forgejo configuration reference, including webhook allowlists and quota subjects](https://forgejo.org/docs/latest/admin/config-cheat-sheet/)
- [Forgejo reverse-proxy and same-origin subpath risks](https://forgejo.org/docs/v17.0/admin/setup/reverse-proxy/)
- [Forgejo webhook user guide](https://forgejo.org/docs/latest/user/repository/webhooks/)
- [Celery task acknowledgement, retry and worker-loss behavior](https://docs.celeryq.dev/en/latest/userguide/tasks.html)
- [Django Storage API](https://docs.djangoproject.com/en/5.2/ref/files/storage/)
