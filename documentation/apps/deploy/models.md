# deploy models

This is the canonical model contract for deploy. Field tables describe the current Django declarations; model notes explain architectural meaning beyond ORM metadata.

## Deploy

Persistent execution/provenance attempt for one Service deployment operation. Once revision is attached, executable inputs are immutable through normal serializers.

Base: BaseModel

| Field | Django type | Null / default / key metadata | Architectural meaning, writers/readers and authority |
|---|---|---|---|
| name | CharField | \\ | n\\|u\\|l\\|l\\|=\\|F\\|a\\|l\\|s\\|e\\|;\\| \\|d\\|e\\|f\\|a\\|u\\|l\\|t\\|=\\|n\\|o\\|n\\|e\\| | Human-facing/domain identifier text. Written through the app's validated API/admin paths and read by UI/search; uniqueness/normalization rules must be preserved. |
| service | ForeignKey | \\ | n\\|u\\|l\\|l\\|=\\|F\\|a\\|l\\|s\\|e\\|;\\| \\|d\\|e\\|f\\|a\\|u\\|l\\|t\\|=\\|n\\|o\\|n\\|e\\|;\\| \\|r\\|e\\|l\\|a\\|t\\|e\\|s\\| \\|t\\|o\\| \\|r\\|e\\|l\\|a\\|t\\|i\\|o\\|n\\| | Service-domain relation. This field connects a resource to desired workload ownership/configuration; it is not proof that runtime currently exists. |
| revision | ForeignKey | \\ | Stores the revision value for Deploy; preserve current writers, readers, null/default semantics and constraints when changing it. |
| created_by | ForeignKey | \\ | Stores the created by value for Deploy; preserve current writers, readers, null/default semantics and constraints when changing it. |
| version | DecimalField | \\ | Stores the version value for Deploy; preserve current writers, readers, null/default semantics and constraints when changing it. |
| zip_file | FileField | \\ | Stores the zip file value for Deploy; preserve current writers, readers, null/default semantics and constraints when changing it. |
| config | JSONField | \\ | Deployment configuration supplied as desired input; sensitive values are handled by the deployment security boundary. |
| started_at | DateTimeField | \\ | Time the operation or phase actually began; null means it has not started. |
| completed_at | DateTimeField | \\ | Time the operation completed; null while pending/running. |
| updated_file_at | DateTimeField | \\ | Stores the updated file at value for Deploy; preserve current writers, readers, null/default semantics and constraints when changing it. |
| status | CharField | \\ | n\\|u\\|l\\|l\\|=\\|F\\|a\\|l\\|s\\|e\\|;\\| \\|d\\|e\\|f\\|a\\|u\\|l\\|t\\|=\\|D\\|e\\|p\\|l\\|o\\|y\\|m\\|e\\|n\\|t\\|S\\|t\\|a\\|t\\|u\\|s\\|C\\|h\\|o\\|i\\|c\\|e\\|s\\|.\\|P\\|E\\|N\\|D\\|I\\|N\\|G\\| | State-machine field. The owning workflow defines legal transitions; readers use the value to decide which operations are safe. |
| stage | CharField | \\ | n\\|u\\|l\\|l\\|=\\|F\\|a\\|l\\|s\\|e\\|;\\| \\|b\\|l\\|a\\|n\\|k\\|=\\|T\\|r\\|u\\|e\\|;\\| \\|d\\|e\\|f\\|a\\|u\\|l\\|t\\|=\\|"\\|i\\|d\\|l\\|e\\|"\\| | State-machine field. The owning workflow defines legal transitions; readers use the value to decide which operations are safe. |
| base_image_wait_started_at | DateTimeField | \\ | Stores the base image wait started at value for Deploy; preserve current writers, readers, null/default semantics and constraints when changing it. |
| base_image_ready_at | DateTimeField | \\ | Stores the base image ready at value for Deploy; preserve current writers, readers, null/default semantics and constraints when changing it. |
| application_started_at | DateTimeField | \\ | Stores the application started at value for Deploy; preserve current writers, readers, null/default semantics and constraints when changing it. |
| progress | PositiveSmallIntegerField | \\ | Stores the progress value for Deploy; preserve current writers, readers, null/default semantics and constraints when changing it. |
| status_message | TextField | \\ | Stores the status message value for Deploy; preserve current writers, readers, null/default semantics and constraints when changing it. |
| error_message | TextField | \\ | Stores the error message value for Deploy; preserve current writers, readers, null/default semantics and constraints when changing it. |
| rollback_status | CharField | \\ | n\\|u\\|l\\|l\\|=\\|F\\|a\\|l\\|s\\|e\\|;\\| \\|d\\|e\\|f\\|a\\|u\\|l\\|t\\|=\\|R\\|o\\|l\\|l\\|b\\|a\\|c\\|k\\|S\\|t\\|a\\|t\\|u\\|s\\|C\\|h\\|o\\|i\\|c\\|e\\|s\\|.\\|N\\|O\\|T\\|_\\|R\\|E\\|Q\\|U\\|I\\|R\\|E\\|D\\| | State-machine field. The owning workflow defines legal transitions; readers use the value to decide which operations are safe. |
| health_status | CharField | \\ | n\\|u\\|l\\|l\\|=\\|F\\|a\\|l\\|s\\|e\\|;\\| \\|b\\|l\\|a\\|n\\|k\\|=\\|T\\|r\\|u\\|e\\|;\\| \\|d\\|e\\|f\\|a\\|u\\|l\\|t\\|=\\|"\\|"\\| | State-machine field. The owning workflow defines legal transitions; readers use the value to decide which operations are safe. |
| container_status | CharField | \\ | n\\|u\\|l\\|l\\|=\\|F\\|a\\|l\\|s\\|e\\|;\\| \\|b\\|l\\|a\\|n\\|k\\|=\\|T\\|r\\|u\\|e\\|;\\| \\|d\\|e\\|f\\|a\\|u\\|l\\|t\\|=\\|"\\|"\\| | State-machine field. The owning workflow defines legal transitions; readers use the value to decide which operations are safe. |
| image_status | CharField | \\ | n\\|u\\|l\\|l\\|=\\|F\\|a\\|l\\|s\\|e\\|;\\| \\|b\\|l\\|a\\|n\\|k\\|=\\|T\\|r\\|u\\|e\\|;\\| \\|d\\|e\\|f\\|a\\|u\\|l\\|t\\|=\\|"\\|"\\| | State-machine field. The owning workflow defines legal transitions; readers use the value to decide which operations are safe. |
| volume_status | CharField | \\ | n\\|u\\|l\\|l\\|=\\|F\\|a\\|l\\|s\\|e\\|;\\| \\|b\\|l\\|a\\|n\\|k\\|=\\|T\\|r\\|u\\|e\\|;\\| \\|d\\|e\\|f\\|a\\|u\\|l\\|t\\|=\\|"\\|"\\| | State-machine field. The owning workflow defines legal transitions; readers use the value to decide which operations are safe. |
| network_status | CharField | \\ | n\\|u\\|l\\|l\\|=\\|F\\|a\\|l\\|s\\|e\\|;\\| \\|b\\|l\\|a\\|n\\|k\\|=\\|T\\|r\\|u\\|e\\|;\\| \\|d\\|e\\|f\\|a\\|u\\|l\\|t\\|=\\|"\\|"\\| | State-machine field. The owning workflow defines legal transitions; readers use the value to decide which operations are safe. |
| cancel_requested | BooleanField | \\ | Stores the cancel requested value for Deploy; preserve current writers, readers, null/default semantics and constraints when changing it. |
| execution_task_id | CharField | \\ | Stores the execution task id value for Deploy; preserve current writers, readers, null/default semantics and constraints when changing it. |
| worker_heartbeat_at | DateTimeField | \\ | Stores the worker heartbeat at value for Deploy; preserve current writers, readers, null/default semantics and constraints when changing it. |
| previous_deploy | ForeignKey | \\ | Stores the previous deploy value for Deploy; preserve current writers, readers, null/default semantics and constraints when changing it. |
| operation | CharField | \\ | Stores the operation value for Deploy; preserve current writers, readers, null/default semantics and constraints when changing it. |
| operation_started_at | DateTimeField | \\ | Stores the operation started at value for Deploy; preserve current writers, readers, null/default semantics and constraints when changing it. |
| operation_resource_id | CharField | \\ | Stores the operation resource id value for Deploy; preserve current writers, readers, null/default semantics and constraints when changing it. |
| operation_previous_resource_id | CharField | \\ | Stores the operation previous resource id value for Deploy; preserve current writers, readers, null/default semantics and constraints when changing it. |
| recovery_metadata | JSONField | \\ | Structured recovery journal describing why/how a deployment was recovered. |

## DeployLog

Deployment event history on the separate deployment_logs database; cross-database scalar ids are intentional.

Base: BaseModel

| Field | Django type | Null / default / key metadata | Architectural meaning, writers/readers and authority |
|---|---|---|---|
| deploy | ForeignKey | \\ | Optional deploy.Deploy correlation; identifies execution history, not desired state. |
| service | ForeignKey | \\ | n\\|u\\|l\\|l\\|=\\|F\\|a\\|l\\|s\\|e\\|;\\| \\|d\\|e\\|f\\|a\\|u\\|l\\|t\\|=\\|n\\|o\\|n\\|e\\|;\\| \\|r\\|e\\|l\\|a\\|t\\|e\\|s\\| \\|t\\|o\\| \\|r\\|e\\|l\\|a\\|t\\|i\\|o\\|n\\| | Service-domain relation. This field connects a resource to desired workload ownership/configuration; it is not proof that runtime currently exists. |
| stage | CharField | \\ | n\\|u\\|l\\|l\\|=\\|F\\|a\\|l\\|s\\|e\\|;\\| \\|d\\|e\\|f\\|a\\|u\\|l\\|t\\|=\\|n\\|o\\|n\\|e\\| | State-machine field. The owning workflow defines legal transitions; readers use the value to decide which operations are safe. |
| event_type | CharField | \\ | Stores the event type value for DeployLog; preserve current writers, readers, null/default semantics and constraints when changing it. |
| level | CharField | \\ | Log severity classification supplied by ingestion. |
| message | TextField | \\ | Persisted log line/message content. |
| progress | PositiveSmallIntegerField | \\ | Stores the progress value for DeployLog; preserve current writers, readers, null/default semantics and constraints when changing it. |
| details | JSONField | \\ | Structured deployment-log metadata for diagnostics, not control-plane authority. |
| exception_type | CharField | \\ | Stores the exception type value for DeployLog; preserve current writers, readers, null/default semantics and constraints when changing it. |
| traceback | TextField | \\ | Stores the traceback value for DeployLog; preserve current writers, readers, null/default semantics and constraints when changing it. |

## BaseRuntimeImageLease

Lease preventing cleanup of a base image while a deployment depends on it.

Base: BaseModel

| Field | Django type | Null / default / key metadata | Architectural meaning, writers/readers and authority |
|---|---|---|---|
| base_image | ForeignKey | \\ | Stores the base image value for BaseRuntimeImageLease; preserve current writers, readers, null/default semantics and constraints when changing it. |
| deployment_id | CharField | \\ | n\\|u\\|l\\|l\\|=\\|F\\|a\\|l\\|s\\|e\\|;\\| \\|d\\|e\\|f\\|a\\|u\\|l\\|t\\|=\\|n\\|o\\|n\\|e\\|;\\| \\|i\\|n\\|d\\|e\\|x\\|e\\|d\\| | Cross-entity correlation/ownership reference. Written when the relation is established and read by authorization, joins and lifecycle workflows. |
| acquired_at | DateTimeField | \\ | Stores the acquired at value for BaseRuntimeImageLease; preserve current writers, readers, null/default semantics and constraints when changing it. |
| released_at | DateTimeField | \\ | Stores the released at value for BaseRuntimeImageLease; preserve current writers, readers, null/default semantics and constraints when changing it. |

## BaseRuntimeImage

Operator-owned shared base-image registry entry keyed by runtime/version/variant/architecture/host and definition fingerprint.

Base: BaseModel

| Field | Django type | Null / default / key metadata | Architectural meaning, writers/readers and authority |
|---|---|---|---|
| logical_runtime | CharField | \\ | Stores the logical runtime value for BaseRuntimeImage; preserve current writers, readers, null/default semantics and constraints when changing it. |
| runtime_version | CharField | \\ | Stores the runtime version value for BaseRuntimeImage; preserve current writers, readers, null/default semantics and constraints when changing it. |
| variant | CharField | \\ | Stores the variant value for BaseRuntimeImage; preserve current writers, readers, null/default semantics and constraints when changing it. |
| architecture | CharField | \\ | Stores the architecture value for BaseRuntimeImage; preserve current writers, readers, null/default semantics and constraints when changing it. |
| docker_host | CharField | \\ | Stores the docker host value for BaseRuntimeImage; preserve current writers, readers, null/default semantics and constraints when changing it. |
| source_image | CharField | \\ | Stores the source image value for BaseRuntimeImage; preserve current writers, readers, null/default semantics and constraints when changing it. |
| image_repository | CharField | \\ | Stores the image repository value for BaseRuntimeImage; preserve current writers, readers, null/default semantics and constraints when changing it. |
| image_tag | CharField | \\ | Stores the image tag value for BaseRuntimeImage; preserve current writers, readers, null/default semantics and constraints when changing it. |
| image_ref | CharField | \\ | Stores the image ref value for BaseRuntimeImage; preserve current writers, readers, null/default semantics and constraints when changing it. |
| image_id | CharField | \\ | Stores the image id value for BaseRuntimeImage; preserve current writers, readers, null/default semantics and constraints when changing it. |
| image_digest | CharField | \\ | Stores the image digest value for BaseRuntimeImage; preserve current writers, readers, null/default semantics and constraints when changing it. |
| status | CharField | \\ | n\\|u\\|l\\|l\\|=\\|F\\|a\\|l\\|s\\|e\\|;\\| \\|d\\|e\\|f\\|a\\|u\\|l\\|t\\|=\\|S\\|t\\|a\\|t\\|u\\|s\\|.\\|P\\|E\\|N\\|D\\|I\\|N\\|G\\| | State-machine field. The owning workflow defines legal transitions; readers use the value to decide which operations are safe. |
| enabled | BooleanField | \\ | Stores the enabled value for BaseRuntimeImage; preserve current writers, readers, null/default semantics and constraints when changing it. |
| auto_build | BooleanField | \\ | Stores the auto build value for BaseRuntimeImage; preserve current writers, readers, null/default semantics and constraints when changing it. |
| rebuild_requested | BooleanField | \\ | Stores the rebuild requested value for BaseRuntimeImage; preserve current writers, readers, null/default semantics and constraints when changing it. |
| rebuild_requested_at | DateTimeField | \\ | Stores the rebuild requested at value for BaseRuntimeImage; preserve current writers, readers, null/default semantics and constraints when changing it. |
| build_started_at | DateTimeField | \\ | Stores the build started at value for BaseRuntimeImage; preserve current writers, readers, null/default semantics and constraints when changing it. |
| build_completed_at | DateTimeField | \\ | Stores the build completed at value for BaseRuntimeImage; preserve current writers, readers, null/default semantics and constraints when changing it. |
| build_count | PositiveIntegerField | \\ | n\\|u\\|l\\|l\\|=\\|F\\|a\\|l\\|s\\|e\\|;\\| \\|d\\|e\\|f\\|a\\|u\\|l\\|t\\|=\\|0\\| | Derived/accounting counter. Treat as cached/ledger-like state and update through the owning operation, not arbitrary form input. |
| build_task_id | CharField | \\ | Stores the build task id value for BaseRuntimeImage; preserve current writers, readers, null/default semantics and constraints when changing it. |
| build_owner_deployment_id | CharField | \\ | n\\|u\\|l\\|l\\|=\\|F\\|a\\|l\\|s\\|e\\|;\\| \\|b\\|l\\|a\\|n\\|k\\|=\\|T\\|r\\|u\\|e\\|;\\| \\|d\\|e\\|f\\|a\\|u\\|l\\|t\\|=\\|"\\|"\\| | Cross-entity correlation/ownership reference. Written when the relation is established and read by authorization, joins and lifecycle workflows. |
| definition_fingerprint | CharField | \\ | Stores the definition fingerprint value for BaseRuntimeImage; preserve current writers, readers, null/default semantics and constraints when changing it. |
| last_error | TextField | \\ | Stores the last error value for BaseRuntimeImage; preserve current writers, readers, null/default semantics and constraints when changing it. |
| last_error_details | JSONField | \\ | Structured base-runtime failure diagnostics, not user-authored runtime configuration. |

## SwarmCluster

Operator inventory/configuration record for a Docker Swarm cluster.

Base: BaseModel

| Field | Django type | Null / default / key metadata | Architectural meaning, writers/readers and authority |
|---|---|---|---|
| name | CharField | \\ | n\\|u\\|l\\|l\\|=\\|F\\|a\\|l\\|s\\|e\\|;\\| \\|d\\|e\\|f\\|a\\|u\\|l\\|t\\|=\\|"\\|d\\|e\\|f\\|a\\|u\\|l\\|t\\|"\\|;\\| \\|u\\|n\\|i\\|q\\|u\\|e\\| | Human-facing/domain identifier text. Written through the app's validated API/admin paths and read by UI/search; uniqueness/normalization rules must be preserved. |
| enabled | BooleanField | \\ | Stores the enabled value for SwarmCluster; preserve current writers, readers, null/default semantics and constraints when changing it. |
| manager_endpoint | CharField | \\ | Stores the manager endpoint value for SwarmCluster; preserve current writers, readers, null/default semantics and constraints when changing it. |
| last_synced_at | DateTimeField | \\ | Stores the last synced at value for SwarmCluster; preserve current writers, readers, null/default semantics and constraints when changing it. |
| last_error | TextField | \\ | Stores the last error value for SwarmCluster; preserve current writers, readers, null/default semantics and constraints when changing it. |

## SwarmNode

Operator desired/observed metadata for one Swarm node; desired availability/labels and observed Docker state are distinct.

Base: BaseModel

| Field | Django type | Null / default / key metadata | Architectural meaning, writers/readers and authority |
|---|---|---|---|
| cluster | ForeignKey | \\ | Stores the cluster value for SwarmNode; preserve current writers, readers, null/default semantics and constraints when changing it. |
| docker_id | CharField | \\ | Stores the docker id value for SwarmNode; preserve current writers, readers, null/default semantics and constraints when changing it. |
| hostname | CharField | \\ | Stores the hostname value for SwarmNode; preserve current writers, readers, null/default semantics and constraints when changing it. |
| role | CharField | \\ | Stores the role value for SwarmNode; preserve current writers, readers, null/default semantics and constraints when changing it. |
| desired_availability | CharField | \\ | Stores the desired availability value for SwarmNode; preserve current writers, readers, null/default semantics and constraints when changing it. |
| observed_availability | CharField | \\ | Stores the observed availability value for SwarmNode; preserve current writers, readers, null/default semantics and constraints when changing it. |
| observed_state | CharField | \\ | Stores the observed state value for SwarmNode; preserve current writers, readers, null/default semantics and constraints when changing it. |
| address | CharField | \\ | Stores the address value for SwarmNode; preserve current writers, readers, null/default semantics and constraints when changing it. |
| labels | JSONField | \\ | Observed Swarm node labels from the latest synchronization. |
| desired_labels | JSONField | \\ | Operator-requested Swarm node labels targeted by reconciliation. |
| cpus | PositiveIntegerField | \\ | Stores the cpus value for SwarmNode; preserve current writers, readers, null/default semantics and constraints when changing it. |
| memory_bytes | BigIntegerField | \\ | Stores the memory bytes value for SwarmNode; preserve current writers, readers, null/default semantics and constraints when changing it. |
| manager_reachable | BooleanField | \\ | Stores the manager reachable value for SwarmNode; preserve current writers, readers, null/default semantics and constraints when changing it. |
| last_synced_at | DateTimeField | \\ | Stores the last synced at value for SwarmNode; preserve current writers, readers, null/default semantics and constraints when changing it. |
| last_error | TextField | \\ | Stores the last error value for SwarmNode; preserve current writers, readers, null/default semantics and constraints when changing it. |

## State, deletion and maintenance rules

The source model definitions call full_clean() on several important saves and define database constraints/indexes in Meta. Deletion behavior is part of the domain contract: read the on_delete declarations above together with the app README before changing cascades, SET_NULL, PROTECT or replacement semantics.

JSON fields are structured contracts. Do not introduce keys by observation from one API response; update the producer, consumer and serializer contract together. Sensitive JSON values are security state and must be redacted or encrypted according to the app rules.

## Implementation versus intent

**Current implementation:** the tables reflect the current master branch model declarations and call-site semantics.

**Architectural intent:** models store durable domain state; runtime observations and transient worker state are separated where the architecture requires it.

**Compatibility behavior:** fields explicitly described as projections, legacy state, or migration bridges must not be interpreted as a second source of truth.

**Do not assume:** a Django field being writable at the ORM level means any API or worker is allowed to mutate it. Workflow ownership and invariants in the app documentation control safe writes.


## Build cache governance models

`src/deploy/models.py::BuildCacheArtifact` records one logical application
image artifact with its User, Service and Deploy ownership, image identity,
size, last-use timestamp, protection flag and reclamation state.

`src/deploy/models.py::BuildCacheQuota` stores an operator override owned by
exactly one User or exactly one Service. Quota, retention and protected
successful-deployment count are optional and inherit the global build-cache
policy when left unset.

The cache policy engine is implemented in `src/deploy/build_cache.py`.
Physical Docker BuildKit storage is global; these models provide logical
tenant accounting and safe application-image retention.

> **Complete field reference:** [field-reference.md](field-reference.md) lists every field explicitly declared in `src/deploy/models.py`, including type, null/blank behavior, defaults, constraints and purpose.
