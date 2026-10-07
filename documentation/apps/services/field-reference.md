# services — model field reference

This page is a source-derived reference of every Django model field declared in `src/services/models.py` at the current `master` revision. It complements [models.md](models.md), which remains the narrative model overview.

Source of truth: `src/services/models.py`. Django/Django-contrib inherited fields are not repeated unless this source file explicitly declares them.

## PrivateNetwork

**Bases:** `BaseModel`  
**Declared fields:** 3

| Field | Django type | DB nullable | Blank | Default | Constraints / relation | Purpose / contract |
|---|---|---:|---:|---|---|---|
| `name` | `CharField` | no | no | `—` | DB non-null, blank not allowed | Human-readable or user-selected name used for identification and UI. |
| `user` | `ForeignKey` | no | no | `—` | DB non-null, blank not allowed, on_delete; on_delete=CASCADE | Associates the record with the user/owner or actor responsible for it. |
| `description` | `TextField` | no | yes | `—` | DB non-null, blank allowed | Human-readable explanation/metadata shown to operators or users. |

### Field-level notes

- `name`: `CharField` with DB non-null, blank not allowed. The model declaration is authoritative for validation and persistence behavior.
- `user`: `ForeignKey` with DB non-null, blank not allowed, on_delete. The model declaration is authoritative for validation and persistence behavior.
- `description`: `TextField` with DB non-null, blank allowed. The model declaration is authoritative for validation and persistence behavior.

## Service

**Bases:** `BaseModel`  
**Declared fields:** 18

| Field | Django type | DB nullable | Blank | Default | Constraints / relation | Purpose / contract |
|---|---|---:|---:|---|---|---|
| `name` | `CharField` | no | no | `—` | DB non-null, blank not allowed, unique | Human-readable or user-selected name used for identification and UI. |
| `user` | `ForeignKey` | no | no | `—` | DB non-null, blank not allowed, on_delete; on_delete=CASCADE | Associates the record with the user/owner or actor responsible for it. |
| `plan` | `ForeignKey` | no | no | `—` | DB non-null, blank not allowed, on_delete; on_delete=CASCADE | Selects the resource/policy envelope used by the record. |
| `network` | `ForeignKey` | yes | no | `—` | DB nullable, blank not allowed, on_delete; related_name=Service; on_delete=RESTRICT | Associates the record with its private/network scope. |
| `read_only` | `BooleanField` | no | no | `True` | DB non-null, blank not allowed | Stores the read only value required by Service for its BooleanField contract. |
| `selected_deploy` | `OneToOneField` | yes | yes | `—` | DB nullable, blank allowed, on_delete; related_name=+; on_delete=SET_NULL | Associates the record with a deployment attempt/provenance record. |
| `selected_deploy_at` | `DateTimeField` | yes | yes | `—` | DB nullable, blank allowed | Associates the record with a deployment attempt/provenance record. |
| `active_revision` | `ForeignKey` | yes | yes | `—` | DB nullable, blank allowed, on_delete; related_name=active_for_services; on_delete=SET_NULL | Stores the active revision value required by Service for its ForeignKey contract. |
| `deploy_started` | `DateTimeField` | yes | yes | `—` | DB nullable, blank allowed | Associates the record with a deployment attempt/provenance record. |
| `deployed_at` | `DateTimeField` | yes | yes | `—` | DB nullable, blank allowed | Associates the record with a deployment attempt/provenance record. |
| `status` | `CharField` | no | no | `SERVICE_STATUS_CHOICES.STOPPED` | DB non-null, blank not allowed, choices | Lifecycle/status discriminator used to decide which operations are legal. |
| `task_id` | `CharField` | yes | yes | `—` | DB nullable, blank allowed, unique | Asynchronous task correlation/ownership identifier. |
| `source_kind` | `CharField` | no | no | `SourceKind.ARCHIVE` | DB non-null, blank not allowed, choices | Stores the source kind value required by Service for its CharField contract. |
| `source_config` | `JSONField` | no | yes | `dict` | DB non-null, blank allowed | Source-specific configuration for how the workload was created. |
| `build_config` | `JSONField` | no | yes | `dict` | DB non-null, blank allowed | Build-time configuration captured or requested for the workload. |
| `runtime_config` | `JSONField` | no | yes | `dict` | DB non-null, blank allowed | Runtime execution settings for the workload. |
| `desired_state` | `CharField` | no | no | `"stopped"` | DB non-null, blank not allowed, choices | Durable user intent for whether the workload should run or stop. |
| `lifecycle_generation` | `PositiveIntegerField` | no | no | `0` | DB non-null, blank not allowed | Monotonic fence used to invalidate stale worker operations. |

### Field-level notes

- `name`: `CharField` with DB non-null, blank not allowed, unique. The model declaration is authoritative for validation and persistence behavior.
- `user`: `ForeignKey` with DB non-null, blank not allowed, on_delete. The model declaration is authoritative for validation and persistence behavior.
- `plan`: `ForeignKey` with DB non-null, blank not allowed, on_delete. The model declaration is authoritative for validation and persistence behavior.
- `network`: `ForeignKey` with DB nullable, blank not allowed, on_delete. The model declaration is authoritative for validation and persistence behavior.
- `read_only`: `BooleanField` with DB non-null, blank not allowed. The model declaration is authoritative for validation and persistence behavior.
- `selected_deploy`: `OneToOneField` with DB nullable, blank allowed, on_delete. The model declaration is authoritative for validation and persistence behavior.
- `selected_deploy_at`: `DateTimeField` with DB nullable, blank allowed. The model declaration is authoritative for validation and persistence behavior.
- `active_revision`: `ForeignKey` with DB nullable, blank allowed, on_delete. The model declaration is authoritative for validation and persistence behavior.
- `deploy_started`: `DateTimeField` with DB nullable, blank allowed. The model declaration is authoritative for validation and persistence behavior.
- `deployed_at`: `DateTimeField` with DB nullable, blank allowed. The model declaration is authoritative for validation and persistence behavior.
- `status`: `CharField` with DB non-null, blank not allowed, choices. The model declaration is authoritative for validation and persistence behavior.
- `task_id`: `CharField` with DB nullable, blank allowed, unique. The model declaration is authoritative for validation and persistence behavior.
- `source_kind`: `CharField` with DB non-null, blank not allowed, choices. The model declaration is authoritative for validation and persistence behavior.
- `source_config`: `JSONField` with DB non-null, blank allowed. The model declaration is authoritative for validation and persistence behavior.
- `build_config`: `JSONField` with DB non-null, blank allowed. The model declaration is authoritative for validation and persistence behavior.
- `runtime_config`: `JSONField` with DB non-null, blank allowed. The model declaration is authoritative for validation and persistence behavior.
- `desired_state`: `CharField` with DB non-null, blank not allowed, choices. The model declaration is authoritative for validation and persistence behavior.
- `lifecycle_generation`: `PositiveIntegerField` with DB non-null, blank not allowed. The model declaration is authoritative for validation and persistence behavior.

## ServiceProcess

**Bases:** `BaseModel`  
**Declared fields:** 11

| Field | Django type | DB nullable | Blank | Default | Constraints / relation | Purpose / contract |
|---|---|---:|---:|---|---|---|
| `service` | `ForeignKey` | no | no | `—` | DB non-null, blank not allowed, on_delete; related_name=processes; on_delete=CASCADE | Associates this record with the durable Service it belongs to or targets. |
| `name` | `CharField` | no | no | `—` | DB non-null, blank not allowed | Human-readable or user-selected name used for identification and UI. |
| `process_type` | `CharField` | no | no | `"custom"` | DB non-null, blank not allowed | Stores the process type value required by ServiceProcess for its CharField contract. |
| `command` | `TextField` | yes | yes | `—` | DB nullable, blank allowed | Stores the command value required by ServiceProcess for its TextField contract. |
| `entrypoint` | `TextField` | yes | yes | `—` | DB nullable, blank allowed | Stores the entrypoint value required by ServiceProcess for its TextField contract. |
| `replicas` | `PositiveIntegerField` | no | no | `1` | DB non-null, blank not allowed | Stores the replicas value required by ServiceProcess for its PositiveIntegerField contract. |
| `enabled` | `BooleanField` | no | no | `True` | DB non-null, blank not allowed | Whether this record is currently enabled for normal use. |
| `environment` | `JSONField` | no | yes | `dict` | DB non-null, blank allowed | Stores the environment value required by ServiceProcess for its JSONField contract. |
| `healthcheck` | `JSONField` | no | yes | `dict` | DB non-null, blank allowed | Stores the healthcheck value required by ServiceProcess for its JSONField contract. |
| `resources` | `JSONField` | no | yes | `dict` | DB non-null, blank allowed | Stores the resources value required by ServiceProcess for its JSONField contract. |
| `metadata` | `JSONField` | no | yes | `dict` | DB non-null, blank allowed | Extensible non-core metadata that does not change the main schema contract. |

### Field-level notes

- `service`: `ForeignKey` with DB non-null, blank not allowed, on_delete. The model declaration is authoritative for validation and persistence behavior.
- `name`: `CharField` with DB non-null, blank not allowed. The model declaration is authoritative for validation and persistence behavior.
- `process_type`: `CharField` with DB non-null, blank not allowed. The model declaration is authoritative for validation and persistence behavior.
- `command`: `TextField` with DB nullable, blank allowed. The model declaration is authoritative for validation and persistence behavior.
- `entrypoint`: `TextField` with DB nullable, blank allowed. The model declaration is authoritative for validation and persistence behavior.
- `replicas`: `PositiveIntegerField` with DB non-null, blank not allowed. The model declaration is authoritative for validation and persistence behavior.
- `enabled`: `BooleanField` with DB non-null, blank not allowed. The model declaration is authoritative for validation and persistence behavior.
- `environment`: `JSONField` with DB non-null, blank allowed. The model declaration is authoritative for validation and persistence behavior.
- `healthcheck`: `JSONField` with DB non-null, blank allowed. The model declaration is authoritative for validation and persistence behavior.
- `resources`: `JSONField` with DB non-null, blank allowed. The model declaration is authoritative for validation and persistence behavior.
- `metadata`: `JSONField` with DB non-null, blank allowed. The model declaration is authoritative for validation and persistence behavior.

## ServiceRevision

**Bases:** `BaseModel`  
**Declared fields:** 19

| Field | Django type | DB nullable | Blank | Default | Constraints / relation | Purpose / contract |
|---|---|---:|---:|---|---|---|
| `service` | `ForeignKey` | no | no | `—` | DB non-null, blank not allowed, on_delete; related_name=revisions; on_delete=CASCADE | Associates this record with the durable Service it belongs to or targets. |
| `revision_number` | `PositiveIntegerField` | no | no | `—` | DB non-null, blank not allowed | Monotonic revision sequence for immutable ServiceRevision history. |
| `state` | `CharField` | no | no | `State.CREATED` | DB non-null, blank not allowed, choices | Internal lifecycle/state-machine discriminator. |
| `source_deploy` | `ForeignKey` | yes | yes | `—` | DB nullable, blank allowed, on_delete; related_name=source_revisions; on_delete=SET_NULL | Associates the record with a deployment attempt/provenance record. |
| `artifact_file` | `FileField` | yes | yes | `—` | DB nullable, blank allowed | Stores the artifact file value required by ServiceRevision for its FileField contract. |
| `created_by` | `ForeignKey` | yes | yes | `—` | DB nullable, blank allowed, on_delete; related_name=service_revisions; on_delete=SET_NULL | Associates the record with the user/owner or actor responsible for it. |
| `config_snapshot` | `JSONField` | no | no | `dict` | DB non-null, blank not allowed | Stores the config snapshot value required by ServiceRevision for its JSONField contract. |
| `process_snapshot` | `JSONField` | no | no | `list` | DB non-null, blank not allowed | Stores the process snapshot value required by ServiceRevision for its JSONField contract. |
| `secret_keys` | `JSONField` | no | no | `list` | DB non-null, blank not allowed | Stores the secret keys value required by ServiceRevision for its JSONField contract. |
| `secret_refs` | `JSONField` | no | yes | `list` | DB non-null, blank allowed | Stores the secret refs value required by ServiceRevision for its JSONField contract. |
| `source_snapshot` | `JSONField` | no | yes | `dict` | DB non-null, blank allowed | Stores the source snapshot value required by ServiceRevision for its JSONField contract. |
| `build_snapshot` | `JSONField` | no | yes | `dict` | DB non-null, blank allowed | Stores the build snapshot value required by ServiceRevision for its JSONField contract. |
| `runtime_snapshot` | `JSONField` | no | yes | `dict` | DB non-null, blank allowed | Stores the runtime snapshot value required by ServiceRevision for its JSONField contract. |
| `environment_snapshot` | `JSONField` | no | yes | `dict` | DB non-null, blank allowed | Stores the environment snapshot value required by ServiceRevision for its JSONField contract. |
| `endpoint_snapshot` | `JSONField` | no | yes | `list` | DB non-null, blank allowed | Stores the endpoint snapshot value required by ServiceRevision for its JSONField contract. |
| `volume_snapshot` | `JSONField` | no | yes | `list` | DB non-null, blank allowed | Associates or configures persistent storage. |
| `network_snapshot` | `JSONField` | no | yes | `list` | DB non-null, blank allowed | Associates the record with its private/network scope. |
| `graph_snapshot` | `JSONField` | no | yes | `dict` | DB non-null, blank allowed | Stores the graph snapshot value required by ServiceRevision for its JSONField contract. |
| `activated_at` | `DateTimeField` | yes | yes | `—` | DB nullable, blank allowed | Timestamp proving when a revision became authoritative. |

### Field-level notes

- `service`: `ForeignKey` with DB non-null, blank not allowed, on_delete. The model declaration is authoritative for validation and persistence behavior.
- `revision_number`: `PositiveIntegerField` with DB non-null, blank not allowed. The model declaration is authoritative for validation and persistence behavior.
- `state`: `CharField` with DB non-null, blank not allowed, choices. The model declaration is authoritative for validation and persistence behavior.
- `source_deploy`: `ForeignKey` with DB nullable, blank allowed, on_delete. The model declaration is authoritative for validation and persistence behavior.
- `artifact_file`: `FileField` with DB nullable, blank allowed. The model declaration is authoritative for validation and persistence behavior.
- `created_by`: `ForeignKey` with DB nullable, blank allowed, on_delete. The model declaration is authoritative for validation and persistence behavior.
- `config_snapshot`: `JSONField` with DB non-null, blank not allowed. The model declaration is authoritative for validation and persistence behavior.
- `process_snapshot`: `JSONField` with DB non-null, blank not allowed. The model declaration is authoritative for validation and persistence behavior.
- `secret_keys`: `JSONField` with DB non-null, blank not allowed. The model declaration is authoritative for validation and persistence behavior.
- `secret_refs`: `JSONField` with DB non-null, blank allowed. The model declaration is authoritative for validation and persistence behavior.
- `source_snapshot`: `JSONField` with DB non-null, blank allowed. The model declaration is authoritative for validation and persistence behavior.
- `build_snapshot`: `JSONField` with DB non-null, blank allowed. The model declaration is authoritative for validation and persistence behavior.
- `runtime_snapshot`: `JSONField` with DB non-null, blank allowed. The model declaration is authoritative for validation and persistence behavior.
- `environment_snapshot`: `JSONField` with DB non-null, blank allowed. The model declaration is authoritative for validation and persistence behavior.
- `endpoint_snapshot`: `JSONField` with DB non-null, blank allowed. The model declaration is authoritative for validation and persistence behavior.
- `volume_snapshot`: `JSONField` with DB non-null, blank allowed. The model declaration is authoritative for validation and persistence behavior.
- `network_snapshot`: `JSONField` with DB non-null, blank allowed. The model declaration is authoritative for validation and persistence behavior.
- `graph_snapshot`: `JSONField` with DB non-null, blank allowed. The model declaration is authoritative for validation and persistence behavior.
- `activated_at`: `DateTimeField` with DB nullable, blank allowed. The model declaration is authoritative for validation and persistence behavior.

## ServiceEnvironmentVariable

**Bases:** `BaseModel`  
**Declared fields:** 7

| Field | Django type | DB nullable | Blank | Default | Constraints / relation | Purpose / contract |
|---|---|---:|---:|---|---|---|
| `service` | `ForeignKey` | no | no | `—` | DB non-null, blank not allowed, on_delete; related_name=environment_variables; on_delete=CASCADE | Associates this record with the durable Service it belongs to or targets. |
| `key` | `CharField` | no | no | `—` | DB non-null, blank not allowed | Stores the key value required by ServiceEnvironmentVariable for its CharField contract. |
| `value` | `TextField` | no | yes | `""` | DB non-null, blank allowed | Stores the value value required by ServiceEnvironmentVariable for its TextField contract. |
| `secret` | `ForeignKey` | yes | yes | `—` | DB nullable, blank allowed, on_delete; related_name=environment_variables; on_delete=SET_NULL | Stores the secret value required by ServiceEnvironmentVariable for its ForeignKey contract. |
| `scope` | `CharField` | no | no | `Scope.RUNTIME` | DB non-null, blank not allowed, choices | Stores the scope value required by ServiceEnvironmentVariable for its CharField contract. |
| `enabled` | `BooleanField` | no | no | `True` | DB non-null, blank not allowed | Whether this record is currently enabled for normal use. |
| `metadata` | `JSONField` | no | yes | `dict` | DB non-null, blank allowed | Extensible non-core metadata that does not change the main schema contract. |

### Field-level notes

- `service`: `ForeignKey` with DB non-null, blank not allowed, on_delete. The model declaration is authoritative for validation and persistence behavior.
- `key`: `CharField` with DB non-null, blank not allowed. The model declaration is authoritative for validation and persistence behavior.
- `value`: `TextField` with DB non-null, blank allowed. The model declaration is authoritative for validation and persistence behavior.
- `secret`: `ForeignKey` with DB nullable, blank allowed, on_delete. The model declaration is authoritative for validation and persistence behavior.
- `scope`: `CharField` with DB non-null, blank not allowed, choices. The model declaration is authoritative for validation and persistence behavior.
- `enabled`: `BooleanField` with DB non-null, blank not allowed. The model declaration is authoritative for validation and persistence behavior.
- `metadata`: `JSONField` with DB non-null, blank allowed. The model declaration is authoritative for validation and persistence behavior.

## ServiceSecret

**Bases:** `BaseModel`  
**Declared fields:** 6

| Field | Django type | DB nullable | Blank | Default | Constraints / relation | Purpose / contract |
|---|---|---:|---:|---|---|---|
| `service` | `ForeignKey` | no | no | `—` | DB non-null, blank not allowed, on_delete; related_name=secrets; on_delete=CASCADE | Associates this record with the durable Service it belongs to or targets. |
| `key` | `CharField` | no | no | `—` | DB non-null, blank not allowed | Stores the key value required by ServiceSecret for its CharField contract. |
| `current_version` | `PositiveIntegerField` | no | no | `0` | DB non-null, blank not allowed | Stores the current version value required by ServiceSecret for its PositiveIntegerField contract. |
| `description` | `CharField` | no | yes | `""` | DB non-null, blank allowed | Human-readable explanation/metadata shown to operators or users. |
| `metadata` | `JSONField` | no | yes | `dict` | DB non-null, blank allowed | Extensible non-core metadata that does not change the main schema contract. |
| `enabled` | `BooleanField` | no | no | `True` | DB non-null, blank not allowed | Whether this record is currently enabled for normal use. |

### Field-level notes

- `service`: `ForeignKey` with DB non-null, blank not allowed, on_delete. The model declaration is authoritative for validation and persistence behavior.
- `key`: `CharField` with DB non-null, blank not allowed. The model declaration is authoritative for validation and persistence behavior.
- `current_version`: `PositiveIntegerField` with DB non-null, blank not allowed. The model declaration is authoritative for validation and persistence behavior.
- `description`: `CharField` with DB non-null, blank allowed. The model declaration is authoritative for validation and persistence behavior.
- `metadata`: `JSONField` with DB non-null, blank allowed. The model declaration is authoritative for validation and persistence behavior.
- `enabled`: `BooleanField` with DB non-null, blank not allowed. The model declaration is authoritative for validation and persistence behavior.

## ServiceSecretVersion

**Bases:** `BaseModel`  
**Declared fields:** 5

| Field | Django type | DB nullable | Blank | Default | Constraints / relation | Purpose / contract |
|---|---|---:|---:|---|---|---|
| `secret` | `ForeignKey` | no | no | `—` | DB non-null, blank not allowed, on_delete; related_name=versions; on_delete=CASCADE | Stores the secret value required by ServiceSecretVersion for its ForeignKey contract. |
| `version` | `PositiveIntegerField` | no | no | `—` | DB non-null, blank not allowed | Stores the version value required by ServiceSecretVersion for its PositiveIntegerField contract. |
| `ciphertext` | `TextField` | no | no | `—` | DB non-null, blank not allowed | Encrypted secret payload rather than plaintext secret material. |
| `created_by` | `ForeignKey` | yes | yes | `—` | DB nullable, blank allowed, on_delete; related_name=service_secret_versions; on_delete=SET_NULL | Associates the record with the user/owner or actor responsible for it. |
| `note` | `CharField` | no | yes | `""` | DB non-null, blank allowed | Stores the note value required by ServiceSecretVersion for its CharField contract. |

### Field-level notes

- `secret`: `ForeignKey` with DB non-null, blank not allowed, on_delete. The model declaration is authoritative for validation and persistence behavior.
- `version`: `PositiveIntegerField` with DB non-null, blank not allowed. The model declaration is authoritative for validation and persistence behavior.
- `ciphertext`: `TextField` with DB non-null, blank not allowed. The model declaration is authoritative for validation and persistence behavior.
- `created_by`: `ForeignKey` with DB nullable, blank allowed, on_delete. The model declaration is authoritative for validation and persistence behavior.
- `note`: `CharField` with DB non-null, blank allowed. The model declaration is authoritative for validation and persistence behavior.

## ServiceEndpoint

**Bases:** `BaseModel`  
**Declared fields:** 12

| Field | Django type | DB nullable | Blank | Default | Constraints / relation | Purpose / contract |
|---|---|---:|---:|---|---|---|
| `service` | `ForeignKey` | no | no | `—` | DB non-null, blank not allowed, on_delete; related_name=endpoints; on_delete=CASCADE | Associates this record with the durable Service it belongs to or targets. |
| `process` | `ForeignKey` | yes | yes | `—` | DB nullable, blank allowed, on_delete; related_name=endpoints; on_delete=SET_NULL | Stores the process value required by ServiceEndpoint for its ForeignKey contract. |
| `name` | `CharField` | no | no | `—` | DB non-null, blank not allowed | Human-readable or user-selected name used for identification and UI. |
| `target_port` | `PositiveIntegerField` | no | no | `—` | DB non-null, blank not allowed | Stores the target port value required by ServiceEndpoint for its PositiveIntegerField contract. |
| `published_port` | `PositiveIntegerField` | yes | yes | `—` | DB nullable, blank allowed | Stores the published port value required by ServiceEndpoint for its PositiveIntegerField contract. |
| `protocol` | `CharField` | no | no | `Protocol.HTTP` | DB non-null, blank not allowed, choices | Stores the protocol value required by ServiceEndpoint for its CharField contract. |
| `exposure` | `CharField` | no | no | `Exposure.PUBLIC` | DB non-null, blank not allowed, choices | Stores the exposure value required by ServiceEndpoint for its CharField contract. |
| `hostname` | `CharField` | no | yes | `""` | DB non-null, blank allowed | Stores the hostname value required by ServiceEndpoint for its CharField contract. |
| `path` | `CharField` | no | yes | `""` | DB non-null, blank allowed | Stores the path value required by ServiceEndpoint for its CharField contract. |
| `tls` | `BooleanField` | no | no | `False` | DB non-null, blank not allowed | Stores the tls value required by ServiceEndpoint for its BooleanField contract. |
| `enabled` | `BooleanField` | no | no | `True` | DB non-null, blank not allowed | Whether this record is currently enabled for normal use. |
| `metadata` | `JSONField` | no | yes | `dict` | DB non-null, blank allowed | Extensible non-core metadata that does not change the main schema contract. |

### Field-level notes

- `service`: `ForeignKey` with DB non-null, blank not allowed, on_delete. The model declaration is authoritative for validation and persistence behavior.
- `process`: `ForeignKey` with DB nullable, blank allowed, on_delete. The model declaration is authoritative for validation and persistence behavior.
- `name`: `CharField` with DB non-null, blank not allowed. The model declaration is authoritative for validation and persistence behavior.
- `target_port`: `PositiveIntegerField` with DB non-null, blank not allowed. The model declaration is authoritative for validation and persistence behavior.
- `published_port`: `PositiveIntegerField` with DB nullable, blank allowed. The model declaration is authoritative for validation and persistence behavior.
- `protocol`: `CharField` with DB non-null, blank not allowed, choices. The model declaration is authoritative for validation and persistence behavior.
- `exposure`: `CharField` with DB non-null, blank not allowed, choices. The model declaration is authoritative for validation and persistence behavior.
- `hostname`: `CharField` with DB non-null, blank allowed. The model declaration is authoritative for validation and persistence behavior.
- `path`: `CharField` with DB non-null, blank allowed. The model declaration is authoritative for validation and persistence behavior.
- `tls`: `BooleanField` with DB non-null, blank not allowed. The model declaration is authoritative for validation and persistence behavior.
- `enabled`: `BooleanField` with DB non-null, blank not allowed. The model declaration is authoritative for validation and persistence behavior.
- `metadata`: `JSONField` with DB non-null, blank allowed. The model declaration is authoritative for validation and persistence behavior.

## ServicePortReservation

**Bases:** `BaseModel`  
**Declared fields:** 6

| Field | Django type | DB nullable | Blank | Default | Constraints / relation | Purpose / contract |
|---|---|---:|---:|---|---|---|
| `service` | `ForeignKey` | no | no | `—` | DB non-null, blank not allowed, on_delete; related_name=port_reservations; on_delete=CASCADE | Associates this record with the durable Service it belongs to or targets. |
| `endpoint` | `OneToOneField` | no | no | `—` | DB non-null, blank not allowed, on_delete; related_name=port_reservation; on_delete=CASCADE | Stores the endpoint value required by ServicePortReservation for its OneToOneField contract. |
| `host_port` | `PositiveIntegerField` | no | no | `—` | DB non-null, blank not allowed | Stores the host port value required by ServicePortReservation for its PositiveIntegerField contract. |
| `protocol` | `CharField` | no | no | `"tcp"` | DB non-null, blank not allowed | Stores the protocol value required by ServicePortReservation for its CharField contract. |
| `state` | `CharField` | no | no | `State.ACTIVE` | DB non-null, blank not allowed, choices | Internal lifecycle/state-machine discriminator. |
| `metadata` | `JSONField` | no | yes | `dict` | DB non-null, blank allowed | Extensible non-core metadata that does not change the main schema contract. |

### Field-level notes

- `service`: `ForeignKey` with DB non-null, blank not allowed, on_delete. The model declaration is authoritative for validation and persistence behavior.
- `endpoint`: `OneToOneField` with DB non-null, blank not allowed, on_delete. The model declaration is authoritative for validation and persistence behavior.
- `host_port`: `PositiveIntegerField` with DB non-null, blank not allowed. The model declaration is authoritative for validation and persistence behavior.
- `protocol`: `CharField` with DB non-null, blank not allowed. The model declaration is authoritative for validation and persistence behavior.
- `state`: `CharField` with DB non-null, blank not allowed, choices. The model declaration is authoritative for validation and persistence behavior.
- `metadata`: `JSONField` with DB non-null, blank allowed. The model declaration is authoritative for validation and persistence behavior.

## ServiceNetworkAttachment

**Bases:** `BaseModel`  
**Declared fields:** 5

| Field | Django type | DB nullable | Blank | Default | Constraints / relation | Purpose / contract |
|---|---|---:|---:|---|---|---|
| `service` | `ForeignKey` | no | no | `—` | DB non-null, blank not allowed, on_delete; related_name=network_attachments; on_delete=CASCADE | Associates this record with the durable Service it belongs to or targets. |
| `network` | `ForeignKey` | no | no | `—` | DB non-null, blank not allowed, on_delete; related_name=service_attachments; on_delete=CASCADE | Associates the record with its private/network scope. |
| `alias` | `CharField` | no | yes | `""` | DB non-null, blank allowed | Stores the alias value required by ServiceNetworkAttachment for its CharField contract. |
| `internal` | `BooleanField` | no | no | `False` | DB non-null, blank not allowed | Stores the internal value required by ServiceNetworkAttachment for its BooleanField contract. |
| `metadata` | `JSONField` | no | yes | `dict` | DB non-null, blank allowed | Extensible non-core metadata that does not change the main schema contract. |

### Field-level notes

- `service`: `ForeignKey` with DB non-null, blank not allowed, on_delete. The model declaration is authoritative for validation and persistence behavior.
- `network`: `ForeignKey` with DB non-null, blank not allowed, on_delete. The model declaration is authoritative for validation and persistence behavior.
- `alias`: `CharField` with DB non-null, blank allowed. The model declaration is authoritative for validation and persistence behavior.
- `internal`: `BooleanField` with DB non-null, blank not allowed. The model declaration is authoritative for validation and persistence behavior.
- `metadata`: `JSONField` with DB non-null, blank allowed. The model declaration is authoritative for validation and persistence behavior.

## DatabaseResource

**Bases:** `BaseModel`  
**Declared fields:** 10

| Field | Django type | DB nullable | Blank | Default | Constraints / relation | Purpose / contract |
|---|---|---:|---:|---|---|---|
| `owner` | `ForeignKey` | no | no | `—` | DB non-null, blank not allowed, on_delete; related_name=database_resources; on_delete=CASCADE | Associates the record with the user/owner or actor responsible for it. |
| `provider_service` | `OneToOneField` | yes | yes | `—` | DB nullable, blank allowed, on_delete; related_name=database_resource; on_delete=SET_NULL | Associates this record with the durable Service it belongs to or targets. |
| `name` | `CharField` | no | no | `—` | DB non-null, blank not allowed | Human-readable or user-selected name used for identification and UI. |
| `engine` | `CharField` | no | no | `—` | DB non-null, blank not allowed, choices | Stores the engine value required by DatabaseResource for its CharField contract. |
| `host` | `CharField` | no | yes | `""` | DB non-null, blank allowed | Stores the host value required by DatabaseResource for its CharField contract. |
| `port` | `PositiveIntegerField` | yes | yes | `—` | DB nullable, blank allowed | Stores the port value required by DatabaseResource for its PositiveIntegerField contract. |
| `database_name` | `CharField` | no | yes | `""` | DB non-null, blank allowed | Associates the record with a database resource or binding. |
| `access_policy` | `JSONField` | no | yes | `dict` | DB non-null, blank allowed | Stores the access policy value required by DatabaseResource for its JSONField contract. |
| `metadata` | `JSONField` | no | yes | `dict` | DB non-null, blank allowed | Extensible non-core metadata that does not change the main schema contract. |
| `status` | `CharField` | no | no | `"provisioning"` | DB non-null, blank not allowed | Lifecycle/status discriminator used to decide which operations are legal. |

### Field-level notes

- `owner`: `ForeignKey` with DB non-null, blank not allowed, on_delete. The model declaration is authoritative for validation and persistence behavior.
- `provider_service`: `OneToOneField` with DB nullable, blank allowed, on_delete. The model declaration is authoritative for validation and persistence behavior.
- `name`: `CharField` with DB non-null, blank not allowed. The model declaration is authoritative for validation and persistence behavior.
- `engine`: `CharField` with DB non-null, blank not allowed, choices. The model declaration is authoritative for validation and persistence behavior.
- `host`: `CharField` with DB non-null, blank allowed. The model declaration is authoritative for validation and persistence behavior.
- `port`: `PositiveIntegerField` with DB nullable, blank allowed. The model declaration is authoritative for validation and persistence behavior.
- `database_name`: `CharField` with DB non-null, blank allowed. The model declaration is authoritative for validation and persistence behavior.
- `access_policy`: `JSONField` with DB non-null, blank allowed. The model declaration is authoritative for validation and persistence behavior.
- `metadata`: `JSONField` with DB non-null, blank allowed. The model declaration is authoritative for validation and persistence behavior.
- `status`: `CharField` with DB non-null, blank not allowed. The model declaration is authoritative for validation and persistence behavior.

## DatabaseCredential

**Bases:** `BaseModel`  
**Declared fields:** 4

| Field | Django type | DB nullable | Blank | Default | Constraints / relation | Purpose / contract |
|---|---|---:|---:|---|---|---|
| `database` | `OneToOneField` | no | no | `—` | DB non-null, blank not allowed, on_delete; related_name=credential; on_delete=CASCADE | Associates the record with a database resource or binding. |
| `username` | `CharField` | no | yes | `""` | DB non-null, blank allowed | Stores the username value required by DatabaseCredential for its CharField contract. |
| `password_ciphertext` | `TextField` | no | yes | `""` | DB non-null, blank allowed | Stores the password ciphertext value required by DatabaseCredential for its TextField contract. |
| `version` | `PositiveIntegerField` | no | no | `1` | DB non-null, blank not allowed | Stores the version value required by DatabaseCredential for its PositiveIntegerField contract. |

### Field-level notes

- `database`: `OneToOneField` with DB non-null, blank not allowed, on_delete. The model declaration is authoritative for validation and persistence behavior.
- `username`: `CharField` with DB non-null, blank allowed. The model declaration is authoritative for validation and persistence behavior.
- `password_ciphertext`: `TextField` with DB non-null, blank allowed. The model declaration is authoritative for validation and persistence behavior.
- `version`: `PositiveIntegerField` with DB non-null, blank not allowed. The model declaration is authoritative for validation and persistence behavior.

## ServiceDatabaseBinding

**Bases:** `BaseModel`  
**Declared fields:** 6

| Field | Django type | DB nullable | Blank | Default | Constraints / relation | Purpose / contract |
|---|---|---:|---:|---|---|---|
| `service` | `ForeignKey` | no | no | `—` | DB non-null, blank not allowed, on_delete; related_name=database_bindings; on_delete=CASCADE | Associates this record with the durable Service it belongs to or targets. |
| `database` | `ForeignKey` | no | no | `—` | DB non-null, blank not allowed, on_delete; related_name=bindings; on_delete=CASCADE | Associates the record with a database resource or binding. |
| `alias` | `CharField` | no | no | `"default"` | DB non-null, blank not allowed | Stores the alias value required by ServiceDatabaseBinding for its CharField contract. |
| `env_prefix` | `CharField` | no | no | `"DB"` | DB non-null, blank not allowed | Stores the env prefix value required by ServiceDatabaseBinding for its CharField contract. |
| `access_mode` | `CharField` | no | no | `"rw"` | DB non-null, blank not allowed | Stores the access mode value required by ServiceDatabaseBinding for its CharField contract. |
| `metadata` | `JSONField` | no | yes | `dict` | DB non-null, blank allowed | Extensible non-core metadata that does not change the main schema contract. |

### Field-level notes

- `service`: `ForeignKey` with DB non-null, blank not allowed, on_delete. The model declaration is authoritative for validation and persistence behavior.
- `database`: `ForeignKey` with DB non-null, blank not allowed, on_delete. The model declaration is authoritative for validation and persistence behavior.
- `alias`: `CharField` with DB non-null, blank not allowed. The model declaration is authoritative for validation and persistence behavior.
- `env_prefix`: `CharField` with DB non-null, blank not allowed. The model declaration is authoritative for validation and persistence behavior.
- `access_mode`: `CharField` with DB non-null, blank not allowed. The model declaration is authoritative for validation and persistence behavior.
- `metadata`: `JSONField` with DB non-null, blank allowed. The model declaration is authoritative for validation and persistence behavior.

## Volume

**Bases:** `BaseModel`  
**Declared fields:** 10

| Field | Django type | DB nullable | Blank | Default | Constraints / relation | Purpose / contract |
|---|---|---:|---:|---|---|---|
| `name` | `CharField` | no | no | `—` | DB non-null, blank not allowed, unique | Human-readable or user-selected name used for identification and UI. |
| `user` | `ForeignKey` | no | no | `—` | DB non-null, blank not allowed, on_delete; on_delete=CASCADE | Associates the record with the user/owner or actor responsible for it. |
| `service` | `ForeignKey` | yes | yes | `—` | DB nullable, blank allowed, on_delete; related_name=volumes; on_delete=SET_NULL | Associates this record with the durable Service it belongs to or targets. |
| `service_attachments` | `JSONField` | no | yes | `dict` | DB non-null, blank allowed | Associates this record with the durable Service it belongs to or targets. |
| `default_bind` | `CharField` | no | yes | `""` | DB non-null, blank allowed | Stores the default bind value required by Volume for its CharField contract. |
| `default_mode` | `CharField` | no | yes | `VOLUME_MODE_CHOICES.READ_WRITE` | DB non-null, blank allowed, choices | Stores the default mode value required by Volume for its CharField contract. |
| `size_mb` | `PositiveIntegerField` | no | no | `—` | DB non-null, blank not allowed | Stores the size mb value required by Volume for its PositiveIntegerField contract. |
| `released_at` | `DateTimeField` | yes | yes | `—` | DB nullable, blank allowed, indexed | Stores the released at value required by Volume for its DateTimeField contract. |
| `reclaim_attempted_at` | `DateTimeField` | yes | yes | `—` | DB nullable, blank allowed | Stores the reclaim attempted at value required by Volume for its DateTimeField contract. |
| `reclaim_error` | `TextField` | no | yes | `""` | DB non-null, blank allowed | Stores the reclaim error value required by Volume for its TextField contract. |

### Field-level notes

- `name`: `CharField` with DB non-null, blank not allowed, unique. The model declaration is authoritative for validation and persistence behavior.
- `user`: `ForeignKey` with DB non-null, blank not allowed, on_delete. The model declaration is authoritative for validation and persistence behavior.
- `service`: `ForeignKey` with DB nullable, blank allowed, on_delete. The model declaration is authoritative for validation and persistence behavior.
- `service_attachments`: `JSONField` with DB non-null, blank allowed. The model declaration is authoritative for validation and persistence behavior.
- `default_bind`: `CharField` with DB non-null, blank allowed. The model declaration is authoritative for validation and persistence behavior.
- `default_mode`: `CharField` with DB non-null, blank allowed, choices. The model declaration is authoritative for validation and persistence behavior.
- `size_mb`: `PositiveIntegerField` with DB non-null, blank not allowed. The model declaration is authoritative for validation and persistence behavior.
- `released_at`: `DateTimeField` with DB nullable, blank allowed, indexed. The model declaration is authoritative for validation and persistence behavior.
- `reclaim_attempted_at`: `DateTimeField` with DB nullable, blank allowed. The model declaration is authoritative for validation and persistence behavior.
- `reclaim_error`: `TextField` with DB non-null, blank allowed. The model declaration is authoritative for validation and persistence behavior.

## ServiceShare

**Bases:** `BaseModel`  
**Declared fields:** 10

| Field | Django type | DB nullable | Blank | Default | Constraints / relation | Purpose / contract |
|---|---|---:|---:|---|---|---|
| `service` | `ForeignKey` | no | no | `—` | DB non-null, blank not allowed, on_delete; related_name=shares; on_delete=CASCADE | Associates this record with the durable Service it belongs to or targets. |
| `group` | `ForeignKey` | yes | yes | `—` | DB nullable, blank allowed, on_delete; related_name=shared_services; on_delete=CASCADE | Stores the group value required by ServiceShare for its ForeignKey contract. |
| `target_user` | `ForeignKey` | yes | yes | `—` | DB nullable, blank allowed, on_delete; related_name=received_service_shares; on_delete=CASCADE | Associates the record with the user/owner or actor responsible for it. |
| `shared_by` | `ForeignKey` | no | no | `—` | DB non-null, blank not allowed, on_delete; related_name=created_service_shares; on_delete=CASCADE | Stores the shared by value required by ServiceShare for its ForeignKey contract. |
| `rules` | `JSONField` | no | yes | `dict` | DB non-null, blank allowed | Stores the rules value required by ServiceShare for its JSONField contract. |
| `is_active` | `BooleanField` | no | no | `True` | DB non-null, blank not allowed | Administrative enable/disable flag. |
| `note` | `CharField` | no | yes | `""` | DB non-null, blank allowed | Stores the note value required by ServiceShare for its CharField contract. |
| `expires_at` | `DateTimeField` | yes | yes | `—` | DB nullable, blank allowed | Time after which the credential/session/invite is no longer valid. |
| `admin_only` | `BooleanField` | no | no | `False` | DB non-null, blank not allowed | Stores the admin only value required by ServiceShare for its BooleanField contract. |
| `preset` | `CharField` | no | yes | `""` | DB non-null, blank allowed | Stores the preset value required by ServiceShare for its CharField contract. |

### Field-level notes

- `service`: `ForeignKey` with DB non-null, blank not allowed, on_delete. The model declaration is authoritative for validation and persistence behavior.
- `group`: `ForeignKey` with DB nullable, blank allowed, on_delete. The model declaration is authoritative for validation and persistence behavior.
- `target_user`: `ForeignKey` with DB nullable, blank allowed, on_delete. The model declaration is authoritative for validation and persistence behavior.
- `shared_by`: `ForeignKey` with DB non-null, blank not allowed, on_delete. The model declaration is authoritative for validation and persistence behavior.
- `rules`: `JSONField` with DB non-null, blank allowed. The model declaration is authoritative for validation and persistence behavior.
- `is_active`: `BooleanField` with DB non-null, blank not allowed. The model declaration is authoritative for validation and persistence behavior.
- `note`: `CharField` with DB non-null, blank allowed. The model declaration is authoritative for validation and persistence behavior.
- `expires_at`: `DateTimeField` with DB nullable, blank allowed. The model declaration is authoritative for validation and persistence behavior.
- `admin_only`: `BooleanField` with DB non-null, blank not allowed. The model declaration is authoritative for validation and persistence behavior.
- `preset`: `CharField` with DB non-null, blank allowed. The model declaration is authoritative for validation and persistence behavior.

## ServiceShareMember

**Bases:** `BaseModel`  
**Declared fields:** 4

| Field | Django type | DB nullable | Blank | Default | Constraints / relation | Purpose / contract |
|---|---|---:|---:|---|---|---|
| `share` | `ForeignKey` | no | no | `—` | DB non-null, blank not allowed, on_delete; related_name=member_rules; on_delete=CASCADE | Stores the share value required by ServiceShareMember for its ForeignKey contract. |
| `user` | `ForeignKey` | no | no | `—` | DB non-null, blank not allowed, on_delete; related_name=service_share_member_rules; on_delete=CASCADE | Associates the record with the user/owner or actor responsible for it. |
| `rules` | `JSONField` | no | yes | `dict` | DB non-null, blank allowed | Stores the rules value required by ServiceShareMember for its JSONField contract. |
| `is_enabled` | `BooleanField` | no | no | `True` | DB non-null, blank not allowed | Stores the is enabled value required by ServiceShareMember for its BooleanField contract. |

### Field-level notes

- `share`: `ForeignKey` with DB non-null, blank not allowed, on_delete. The model declaration is authoritative for validation and persistence behavior.
- `user`: `ForeignKey` with DB non-null, blank not allowed, on_delete. The model declaration is authoritative for validation and persistence behavior.
- `rules`: `JSONField` with DB non-null, blank allowed. The model declaration is authoritative for validation and persistence behavior.
- `is_enabled`: `BooleanField` with DB non-null, blank not allowed. The model declaration is authoritative for validation and persistence behavior.

## ServiceShareEvent

**Bases:** `BaseModel`  
**Declared fields:** 5

| Field | Django type | DB nullable | Blank | Default | Constraints / relation | Purpose / contract |
|---|---|---:|---:|---|---|---|
| `share` | `ForeignKey` | no | no | `—` | DB non-null, blank not allowed, on_delete; related_name=events; on_delete=CASCADE | Stores the share value required by ServiceShareEvent for its ForeignKey contract. |
| `actor` | `ForeignKey` | yes | yes | `—` | DB nullable, blank allowed, on_delete; related_name=+; on_delete=SET_NULL | Stores the actor value required by ServiceShareEvent for its ForeignKey contract. |
| `action` | `CharField` | no | no | `—` | DB non-null, blank not allowed | Stores the action value required by ServiceShareEvent for its CharField contract. |
| `message` | `TextField` | no | yes | `""` | DB non-null, blank allowed | Associates the record with a message or message history. |
| `metadata` | `JSONField` | no | yes | `dict` | DB non-null, blank allowed | Extensible non-core metadata that does not change the main schema contract. |

### Field-level notes

- `share`: `ForeignKey` with DB non-null, blank not allowed, on_delete. The model declaration is authoritative for validation and persistence behavior.
- `actor`: `ForeignKey` with DB nullable, blank allowed, on_delete. The model declaration is authoritative for validation and persistence behavior.
- `action`: `CharField` with DB non-null, blank not allowed. The model declaration is authoritative for validation and persistence behavior.
- `message`: `TextField` with DB non-null, blank allowed. The model declaration is authoritative for validation and persistence behavior.
- `metadata`: `JSONField` with DB non-null, blank allowed. The model declaration is authoritative for validation and persistence behavior.

## ShellSession

**Bases:** `BaseModel`  
**Declared fields:** 11

| Field | Django type | DB nullable | Blank | Default | Constraints / relation | Purpose / contract |
|---|---|---:|---:|---|---|---|
| `service` | `ForeignKey` | no | no | `—` | DB non-null, blank not allowed, on_delete; related_name=shell_sessions; on_delete=CASCADE | Associates this record with the durable Service it belongs to or targets. |
| `user` | `ForeignKey` | no | no | `—` | DB non-null, blank not allowed, on_delete; related_name=shell_sessions; on_delete=CASCADE | Associates the record with the user/owner or actor responsible for it. |
| `token_hash` | `CharField` | no | no | `—` | DB non-null, blank not allowed, unique | Stores the token hash value required by ShellSession for its CharField contract. |
| `platform` | `CharField` | no | no | `—` | DB non-null, blank not allowed | Stores the platform value required by ShellSession for its CharField contract. |
| `root_path` | `CharField` | no | no | `"/app"` | DB non-null, blank not allowed | Stores the root path value required by ShellSession for its CharField contract. |
| `workdir` | `CharField` | no | no | `"/app"` | DB non-null, blank not allowed | Stores the workdir value required by ShellSession for its CharField contract. |
| `mode` | `CharField` | no | no | `Mode.RESTRICTED` | DB non-null, blank not allowed, choices | Stores the mode value required by ShellSession for its CharField contract. |
| `status` | `CharField` | no | no | `Status.ACTIVE` | DB non-null, blank not allowed, choices | Lifecycle/status discriminator used to decide which operations are legal. |
| `last_used_at` | `DateTimeField` | no | no | `timezone.now` | DB non-null, blank not allowed | Most recent use timestamp for access/reconciliation/cleanup decisions. |
| `expires_at` | `DateTimeField` | no | no | `—` | DB non-null, blank not allowed | Time after which the credential/session/invite is no longer valid. |
| `closed_at` | `DateTimeField` | yes | yes | `—` | DB nullable, blank allowed | Stores the closed at value required by ShellSession for its DateTimeField contract. |

### Field-level notes

- `service`: `ForeignKey` with DB non-null, blank not allowed, on_delete. The model declaration is authoritative for validation and persistence behavior.
- `user`: `ForeignKey` with DB non-null, blank not allowed, on_delete. The model declaration is authoritative for validation and persistence behavior.
- `token_hash`: `CharField` with DB non-null, blank not allowed, unique. The model declaration is authoritative for validation and persistence behavior.
- `platform`: `CharField` with DB non-null, blank not allowed. The model declaration is authoritative for validation and persistence behavior.
- `root_path`: `CharField` with DB non-null, blank not allowed. The model declaration is authoritative for validation and persistence behavior.
- `workdir`: `CharField` with DB non-null, blank not allowed. The model declaration is authoritative for validation and persistence behavior.
- `mode`: `CharField` with DB non-null, blank not allowed, choices. The model declaration is authoritative for validation and persistence behavior.
- `status`: `CharField` with DB non-null, blank not allowed, choices. The model declaration is authoritative for validation and persistence behavior.
- `last_used_at`: `DateTimeField` with DB non-null, blank not allowed. The model declaration is authoritative for validation and persistence behavior.
- `expires_at`: `DateTimeField` with DB non-null, blank not allowed. The model declaration is authoritative for validation and persistence behavior.
- `closed_at`: `DateTimeField` with DB nullable, blank allowed. The model declaration is authoritative for validation and persistence behavior.

## ShellAuditEvent

**Bases:** `BaseModel`  
**Declared fields:** 12

| Field | Django type | DB nullable | Blank | Default | Constraints / relation | Purpose / contract |
|---|---|---:|---:|---|---|---|
| `service` | `ForeignKey` | no | no | `—` | DB non-null, blank not allowed, on_delete; related_name=shell_audit_events; on_delete=CASCADE | Associates this record with the durable Service it belongs to or targets. |
| `user` | `ForeignKey` | yes | yes | `—` | DB nullable, blank allowed, on_delete; related_name=shell_audit_events; on_delete=SET_NULL | Associates the record with the user/owner or actor responsible for it. |
| `session` | `ForeignKey` | yes | yes | `—` | DB nullable, blank allowed, on_delete; related_name=audit_events; on_delete=SET_NULL | Stores the session value required by ShellAuditEvent for its ForeignKey contract. |
| `action` | `CharField` | no | no | `—` | DB non-null, blank not allowed, indexed, choices | Stores the action value required by ShellAuditEvent for its CharField contract. |
| `command` | `TextField` | no | yes | `""` | DB non-null, blank allowed | Stores the command value required by ShellAuditEvent for its TextField contract. |
| `path` | `CharField` | no | yes | `""` | DB non-null, blank allowed | Stores the path value required by ShellAuditEvent for its CharField contract. |
| `cwd` | `CharField` | no | yes | `""` | DB non-null, blank allowed | Stores the cwd value required by ShellAuditEvent for its CharField contract. |
| `exit_code` | `IntegerField` | yes | yes | `—` | DB nullable, blank allowed | Stores the exit code value required by ShellAuditEvent for its IntegerField contract. |
| `success` | `BooleanField` | no | no | `True` | DB non-null, blank not allowed | Stores the success value required by ShellAuditEvent for its BooleanField contract. |
| `detail` | `TextField` | no | yes | `""` | DB non-null, blank allowed | Stores the detail value required by ShellAuditEvent for its TextField contract. |
| `meta` | `JSONField` | no | yes | `dict` | DB non-null, blank allowed | Stores the meta value required by ShellAuditEvent for its JSONField contract. |
| `output_preview` | `TextField` | no | yes | `""` | DB non-null, blank allowed | Stores the output preview value required by ShellAuditEvent for its TextField contract. |

### Field-level notes

- `service`: `ForeignKey` with DB non-null, blank not allowed, on_delete. The model declaration is authoritative for validation and persistence behavior.
- `user`: `ForeignKey` with DB nullable, blank allowed, on_delete. The model declaration is authoritative for validation and persistence behavior.
- `session`: `ForeignKey` with DB nullable, blank allowed, on_delete. The model declaration is authoritative for validation and persistence behavior.
- `action`: `CharField` with DB non-null, blank not allowed, indexed, choices. The model declaration is authoritative for validation and persistence behavior.
- `command`: `TextField` with DB non-null, blank allowed. The model declaration is authoritative for validation and persistence behavior.
- `path`: `CharField` with DB non-null, blank allowed. The model declaration is authoritative for validation and persistence behavior.
- `cwd`: `CharField` with DB non-null, blank allowed. The model declaration is authoritative for validation and persistence behavior.
- `exit_code`: `IntegerField` with DB nullable, blank allowed. The model declaration is authoritative for validation and persistence behavior.
- `success`: `BooleanField` with DB non-null, blank not allowed. The model declaration is authoritative for validation and persistence behavior.
- `detail`: `TextField` with DB non-null, blank allowed. The model declaration is authoritative for validation and persistence behavior.
- `meta`: `JSONField` with DB non-null, blank allowed. The model declaration is authoritative for validation and persistence behavior.
- `output_preview`: `TextField` with DB non-null, blank allowed. The model declaration is authoritative for validation and persistence behavior.

## Reading rules

- **DB nullable** means the database may store NULL; **Blank** is a Django validation/form contract and is not equivalent to NULL.
- A default may be a callable (for example `dict`, `timezone.now`, or a project helper), so the displayed expression is not necessarily the stored value at declaration time.
- JSON fields are intentionally flexible and their detailed semantic contract belongs in the app/domain documentation; this table records the field's persistence role.
