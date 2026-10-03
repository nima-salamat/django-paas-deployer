# services models

This document is the canonical field/authority map for the durable workload domain. JSON fields are structured snapshots/config contracts; historical revisions are not mutable configuration stores.

## PrivateNetwork

user owns the network; name is the logical human name, description is presentation. get_docker_network_name derives runtime identity from model id/name; Docker state itself is not stored as authority here.

## Service

| Field | Meaning / writer / reader / authority |
|---|---|
| name | Unique durable service identity used by APIs/runtime naming. Written at creation. |
| user | Owner User FK; primary authorization scope. |
| plan | Customer policy envelope; consumers enforce ceilings. |
| network | Optional default network relation; deleting a referenced PrivateNetwork is restricted while the Service exists; compound User deletion can remove both safely. Runtime graph may also include explicit attachments. |
| read_only | Compatibility/admin presentation flag; persisted default is true and must remain deterministic across environments; runtime overrides are explicit. |
| selected_deploy | Compatibility projection of selected/current deploy. Never treat as replacement for active_revision. |
| selected_deploy_at | Timestamp for projection change; derived audit state. |
| active_revision | Authoritative currently active executable snapshot. Updated by fenced activation. |
| deploy_started / deployed_at | Lifecycle timestamps. They describe prior/current execution, not desired state. |
| status | Current Service lifecycle status (stopped/queued/deploying/running/failed/stopping; succeeded retained for compatibility). |
| task_id | Legacy/current task correlation. Never use it as the only ownership fence. |
| source_kind | archive/git/dockerfile/image/compose/catalog/generated; selects source interpretation. |
| source_config | Normalized source metadata consumed by planning; no runtime Docker state belongs here. |
| build_config | Desired build inputs; becomes revision snapshot then plan/build input. |
| runtime_config | Desired runtime inputs; becomes revision snapshot then runtime policy input. |
| desired_state | stopped/running/deleted intent. It is independent of observed status. |
| lifecycle_generation | Monotonic desired-state fence; stale workers must not overwrite newer intent. |

## ServiceProcess

service/name is unique. process_type, command, entrypoint, replicas, enabled and structured environment/healthcheck/resources/metadata describe desired process behavior. replicas is currently constrained to 1 and Swarm rejects other values. to_snapshot() is the source for revision process_snapshot.

## ServiceRevision

| Field | Meaning |
|---|---|
| service | owning Service |
| revision_number | monotonic per-Service executable version |
| state | created/active/superseded/failed lifecycle metadata |
| source_deploy | historical provenance only; revision reproduction must not require it |
| artifact_file | immutable source artifact owned by revision |
| created_by | actor provenance |
| config_snapshot/process_snapshot | normalized executable configuration |
| secret_keys/secret_refs | secret identity/version references; plaintext is not revision policy |
| source/build/runtime/environment/endpoint/volume/network/graph_snapshot | structured executable snapshot layers used by planning |
| activated_at | activation audit time |

save() rejects mutation of all executable snapshot fields after creation.

## Environment and secrets

ServiceEnvironmentVariable is unique by service/key; scope is build/runtime/both; secret, when set, is authoritative over plaintext value. ServiceSecret is unique by service/key and tracks current_version. ServiceSecretVersion is immutable and stores ciphertext; set_value encrypts, get_value decrypts.

## Endpoints and networks

ServiceEndpoint binds optional process, target_port, published_port, protocol (http/https/tcp/udp/ws), exposure (public/internal), hostname/path/tls/enabled and metadata. clean() enforces port range and protocol/path/TLS combinations.

ServicePortReservation binds one endpoint and reserves an active host_port/protocol pair; RELEASED is historical release state.

ServiceNetworkAttachment uniquely binds Service + PrivateNetwork and stores alias/internal/metadata.

## Databases

DatabaseResource belongs to a User and optionally a provider Service. engine is mysql/mariadb/postgresql/mongodb/redis/oracle; access_policy/metadata are structured controls; status tracks provisioning/readiness.

DatabaseCredential is one-to-one encrypted credential material. ServiceDatabaseBinding links a workload to a database with alias/env_prefix/access_mode/metadata.

## Volume

Volume is owned by User and by at most one Service. size_mb is the logical quota allocation. service_attachments has at most one service-id key containing bind/mode metadata.

Soft detach clears mount metadata but keeps service ownership and therefore continues counting against Service.plan storage. release_from_service clears ownership and marks released_at so allocation can be reclaimed. Reassignment is forbidden without release. Size changes after backend provisioning are allowed only when storage capabilities verify safe resize.

## Sharing

ServiceShare links exactly one Service to exactly one Messenger group OR one target User. rules is normalized action policy; preset is a named rule set; expires_at/is_active/admin_only affect effective access. ServiceShareMember stores per-member overrides inside group shares. ServiceShareEvent records audit history.

## Shell

ShellSession and ShellAuditEvent store restricted shell capability/audit state. Shell access is always resolved against ServiceShare/owner permissions; the session token is capability state, not user identity.

## Deletion/authority

Foreign-key cascades remove subordinate durable state according to the declarations above. Signals coordinate deployment cancellation and runtime cleanup for Services/Volumes/PrivateNetworks; Service deletion is fail-closed for persistent volumes. Runtime resources are not the Service database source of truth.

Source: src/services/models.py.


## Catalog-managed Services

A `Service` with `source_kind=catalog` remains a normal mutable desired-state object, but its execution ownership is constrained by `ApplicationInstanceService`. Catalog-owned plan, network and provenance metadata cannot be changed independently, and direct deletion is rejected while the application binding exists. Mutable runtime configuration still flows through the normal `ServiceRevision -> Deploy` pipeline.
