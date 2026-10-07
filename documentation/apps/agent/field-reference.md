# agent — complete model field reference

Source-derived from `src/agent/models.py` on `master`. This supplements [models.md](models.md) with a field-by-field persistence and validation reference. Only fields explicitly declared by this source file are listed; fields inherited from Django or project base classes are noted in the inheritance section.

## Agent

**Bases:** `BaseModel`  
**Declared fields:** 10

| Field | Type | DB NULL | Blank | Default | Constraints | Purpose / why it exists |
|---|---|---:|---:|---|---|---|
| `user` | `ForeignKey` | no | no | `—` | DB non-null, blank not allowed; related_name=agents; on_delete=CASCADE | Relationship to the owning/target domain object required by this model. |
| `name` | `CharField` | no | no | `—` | DB non-null, blank not allowed | Human-readable name used to identify the record. |
| `description` | `TextField` | no | yes | `""` | DB non-null, blank allowed | Human-readable explanation or metadata. |
| `status` | `CharField` | no | no | `Status.ACTIVE` | DB non-null, blank not allowed, indexed, choices; choices | Lifecycle/status discriminator for legal operations. |
| `provisioning_source` | `CharField` | no | no | `ProvisioningSource.LEGACY` | DB non-null, blank not allowed, indexed, choices; choices | Stores the provisioning source required by the Agent contract. |
| `scopes` | `JSONField` | no | yes | `default_agent_scopes` | DB non-null, blank allowed | Stores the scopes required by the Agent contract. |
| `metadata` | `JSONField` | no | yes | `dict` | DB non-null, blank allowed | Extensible non-core metadata. |
| `last_used_at` | `DateTimeField` | yes | yes | `—` | DB nullable, blank allowed, indexed | Most recent access/use timestamp. |
| `disabled_at` | `DateTimeField` | yes | yes | `—` | DB nullable, blank allowed | Stores the disabled at required by the Agent contract. |
| `revoked_at` | `DateTimeField` | yes | yes | `—` | DB nullable, blank allowed | When access was explicitly revoked. |

### Declaration details

- `user`: `ForeignKey` — declaration: `settings.AUTH_USER_MODEL,on_delete=models.CASCADE,related_name="agents"`
- `name`: `CharField` — declaration: `max_length=100`
- `description`: `TextField` — declaration: `blank=True,default=""`
- `status`: `CharField` — declaration: `max_length=16,choices=Status.choices,default=Status.ACTIVE,db_index=True`
- `provisioning_source`: `CharField` — declaration: `max_length=24,choices=ProvisioningSource.choices,default=ProvisioningSource.LEGACY,db_index=True`
- `scopes`: `JSONField` — declaration: `default=default_agent_scopes,blank=True`
- `metadata`: `JSONField` — declaration: `default=dict,blank=True`
- `last_used_at`: `DateTimeField` — declaration: `null=True,blank=True,db_index=True`
- `disabled_at`: `DateTimeField` — declaration: `null=True,blank=True`
- `revoked_at`: `DateTimeField` — declaration: `null=True,blank=True`

## AgentCredential

**Bases:** `BaseModel`  
**Declared fields:** 9

| Field | Type | DB NULL | Blank | Default | Constraints | Purpose / why it exists |
|---|---|---:|---:|---|---|---|
| `agent` | `ForeignKey` | no | no | `—` | DB non-null, blank not allowed; related_name=credentials; on_delete=CASCADE | Relationship to the owning/target domain object required by this model. |
| `token_prefix` | `CharField` | no | no | `—` | DB non-null, blank not allowed, indexed | Stores the token prefix required by the AgentCredential contract. |
| `token_hash` | `CharField` | no | no | `—` | DB non-null, blank not allowed, unique | One-way digest used to validate a credential without storing the secret. |
| `token_type` | `CharField` | no | no | `TokenType.ACCESS` | DB non-null, blank not allowed, choices; choices | Stores the token type required by the AgentCredential contract. |
| `expires_at` | `DateTimeField` | yes | yes | `—` | DB nullable, blank allowed, indexed | Time after which the credential/session/invite is invalid. |
| `revoked_at` | `DateTimeField` | yes | yes | `—` | DB nullable, blank allowed, indexed | When access was explicitly revoked. |
| `last_used_at` | `DateTimeField` | yes | yes | `—` | DB nullable, blank allowed, indexed | Most recent access/use timestamp. |
| `last_used_ip` | `GenericIPAddressField` | yes | yes | `—` | DB nullable, blank allowed | Stores the last used ip required by the AgentCredential contract. |
| `metadata` | `JSONField` | no | yes | `dict` | DB non-null, blank allowed | Extensible non-core metadata. |

### Declaration details

- `agent`: `ForeignKey` — declaration: `Agent,on_delete=models.CASCADE,related_name="credentials"`
- `token_prefix`: `CharField` — declaration: `max_length=32,db_index=True`
- `token_hash`: `CharField` — declaration: `max_length=64,unique=True,editable=False`
- `token_type`: `CharField` — declaration: `max_length=16,choices=TokenType.choices,default=TokenType.ACCESS`
- `expires_at`: `DateTimeField` — declaration: `null=True,blank=True,db_index=True`
- `revoked_at`: `DateTimeField` — declaration: `null=True,blank=True,db_index=True`
- `last_used_at`: `DateTimeField` — declaration: `null=True,blank=True,db_index=True`
- `last_used_ip`: `GenericIPAddressField` — declaration: `null=True,blank=True`
- `metadata`: `JSONField` — declaration: `default=dict,blank=True`

## AgentEnrollmentToken

**Bases:** `BaseModel`  
**Declared fields:** 6

| Field | Type | DB NULL | Blank | Default | Constraints | Purpose / why it exists |
|---|---|---:|---:|---|---|---|
| `agent` | `ForeignKey` | no | no | `—` | DB non-null, blank not allowed; related_name=enrollments; on_delete=CASCADE | Relationship to the owning/target domain object required by this model. |
| `token_prefix` | `CharField` | no | no | `—` | DB non-null, blank not allowed, indexed | Stores the token prefix required by the AgentEnrollmentToken contract. |
| `token_hash` | `CharField` | no | no | `—` | DB non-null, blank not allowed, unique | One-way digest used to validate a credential without storing the secret. |
| `expires_at` | `DateTimeField` | no | no | `—` | DB non-null, blank not allowed, indexed | Time after which the credential/session/invite is invalid. |
| `used_at` | `DateTimeField` | yes | yes | `—` | DB nullable, blank allowed, indexed | Stores the used at required by the AgentEnrollmentToken contract. |
| `issued_from_ip` | `GenericIPAddressField` | yes | yes | `—` | DB nullable, blank allowed | Stores the issued from ip required by the AgentEnrollmentToken contract. |

### Declaration details

- `agent`: `ForeignKey` — declaration: `Agent,on_delete=models.CASCADE,related_name="enrollments"`
- `token_prefix`: `CharField` — declaration: `max_length=32,db_index=True`
- `token_hash`: `CharField` — declaration: `max_length=64,unique=True,editable=False`
- `expires_at`: `DateTimeField` — declaration: `db_index=True`
- `used_at`: `DateTimeField` — declaration: `null=True,blank=True,db_index=True`
- `issued_from_ip`: `GenericIPAddressField` — declaration: `null=True,blank=True`

## AgentAuditEvent

**Bases:** `BaseModel`  
**Declared fields:** 18

| Field | Type | DB NULL | Blank | Default | Constraints | Purpose / why it exists |
|---|---|---:|---:|---|---|---|
| `agent` | `ForeignKey` | yes | yes | `—` | DB nullable, blank allowed; related_name=audit_events; on_delete=SET_NULL | Relationship to the owning/target domain object required by this model. |
| `user` | `ForeignKey` | yes | yes | `—` | DB nullable, blank allowed; related_name=agent_audit_events; on_delete=SET_NULL | Relationship to the owning/target domain object required by this model. |
| `credential` | `ForeignKey` | yes | yes | `—` | DB nullable, blank allowed; related_name=audit_events; on_delete=SET_NULL | Relationship to the owning/target domain object required by this model. |
| `action` | `CharField` | no | no | `—` | DB non-null, blank not allowed, indexed | Stores the action required by the AgentAuditEvent contract. |
| `resource_type` | `CharField` | no | yes | `""` | DB non-null, blank allowed | Stores the resource type required by the AgentAuditEvent contract. |
| `resource_id` | `CharField` | no | yes | `""` | DB non-null, blank allowed | Stores the resource id required by the AgentAuditEvent contract. |
| `request_id` | `CharField` | no | no | `—` | DB non-null, blank not allowed, indexed | Stores the request id required by the AgentAuditEvent contract. |
| `occurred_at` | `DateTimeField` | no | no | `—` | DB non-null, blank not allowed, indexed | Stores the occurred at required by the AgentAuditEvent contract. |
| `success` | `BooleanField` | no | no | `False` | DB non-null, blank not allowed, indexed | Stores the success required by the AgentAuditEvent contract. |
| `http_status` | `PositiveSmallIntegerField` | yes | yes | `—` | DB nullable, blank allowed | Stores the http status required by the AgentAuditEvent contract. |
| `error_code` | `CharField` | no | yes | `""` | DB non-null, blank allowed | Stores the error code required by the AgentAuditEvent contract. |
| `failure_domain` | `CharField` | no | yes | `""` | DB non-null, blank allowed | Stores the failure domain required by the AgentAuditEvent contract. |
| `retryability` | `CharField` | no | yes | `""` | DB non-null, blank allowed | Stores the retryability required by the AgentAuditEvent contract. |
| `visibility` | `CharField` | no | yes | `"client"` | DB non-null, blank allowed | Stores the visibility required by the AgentAuditEvent contract. |
| `resource_effect` | `CharField` | no | yes | `"unchanged"` | DB non-null, blank allowed | Stores the resource effect required by the AgentAuditEvent contract. |
| `certainty` | `CharField` | no | yes | `"known"` | DB non-null, blank allowed | Stores the certainty required by the AgentAuditEvent contract. |
| `duration_ms` | `PositiveIntegerField` | yes | yes | `—` | DB nullable, blank allowed | Stores the duration ms required by the AgentAuditEvent contract. |
| `metadata` | `JSONField` | no | yes | `dict` | DB non-null, blank allowed | Extensible non-core metadata. |

### Declaration details

- `agent`: `ForeignKey` — declaration: `Agent,null=True,blank=True,on_delete=models.SET_NULL,related_name="audit_events"`
- `user`: `ForeignKey` — declaration: `settings.AUTH_USER_MODEL,null=True,blank=True,on_delete=models.SET_NULL,related_name="agent_audit_events"`
- `credential`: `ForeignKey` — declaration: `AgentCredential,null=True,blank=True,on_delete=models.SET_NULL,related_name="audit_events"`
- `action`: `CharField` — declaration: `max_length=96,db_index=True`
- `resource_type`: `CharField` — declaration: `max_length=64,blank=True,default=""`
- `resource_id`: `CharField` — declaration: `max_length=255,blank=True,default=""`
- `request_id`: `CharField` — declaration: `max_length=64,db_index=True`
- `occurred_at`: `DateTimeField` — declaration: `auto_now_add=True,db_index=True`
- `success`: `BooleanField` — declaration: `default=False,db_index=True`
- `http_status`: `PositiveSmallIntegerField` — declaration: `null=True,blank=True`
- `error_code`: `CharField` — declaration: `max_length=96,blank=True,default=""`
- `failure_domain`: `CharField` — declaration: `max_length=32,blank=True,default=""`
- `retryability`: `CharField` — declaration: `max_length=16,blank=True,default=""`
- `visibility`: `CharField` — declaration: `max_length=16,blank=True,default="client"`
- `resource_effect`: `CharField` — declaration: `max_length=32,blank=True,default="unchanged"`
- `certainty`: `CharField` — declaration: `max_length=16,blank=True,default="known"`
- `duration_ms`: `PositiveIntegerField` — declaration: `null=True,blank=True`
- `metadata`: `JSONField` — declaration: `default=dict,blank=True`

## AgentIdempotencyRecord

**Bases:** `BaseModel`  
**Declared fields:** 9

| Field | Type | DB NULL | Blank | Default | Constraints | Purpose / why it exists |
|---|---|---:|---:|---|---|---|
| `agent` | `ForeignKey` | no | no | `—` | DB non-null, blank not allowed; related_name=idempotency_records; on_delete=CASCADE | Relationship to the owning/target domain object required by this model. |
| `key` | `CharField` | no | no | `—` | DB non-null, blank not allowed | Stable configuration/lookup key. |
| `method` | `CharField` | no | no | `—` | DB non-null, blank not allowed | Stores the method required by the AgentIdempotencyRecord contract. |
| `path` | `CharField` | no | no | `—` | DB non-null, blank not allowed | Stores the path required by the AgentIdempotencyRecord contract. |
| `request_hash` | `CharField` | no | no | `—` | DB non-null, blank not allowed | Stores the request hash required by the AgentIdempotencyRecord contract. |
| `state` | `CharField` | no | no | `State.PROCESSING` | DB non-null, blank not allowed, choices; choices | Internal lifecycle/state-machine discriminator. |
| `status_code` | `PositiveSmallIntegerField` | yes | yes | `—` | DB nullable, blank allowed | Stores the status code required by the AgentIdempotencyRecord contract. |
| `response_body` | `JSONField` | yes | yes | `—` | DB nullable, blank allowed | Stores the response body required by the AgentIdempotencyRecord contract. |
| `expires_at` | `DateTimeField` | no | no | `—` | DB non-null, blank not allowed, indexed | Time after which the credential/session/invite is invalid. |

### Declaration details

- `agent`: `ForeignKey` — declaration: `Agent,on_delete=models.CASCADE,related_name="idempotency_records"`
- `key`: `CharField` — declaration: `max_length=255`
- `method`: `CharField` — declaration: `max_length=16`
- `path`: `CharField` — declaration: `max_length=512`
- `request_hash`: `CharField` — declaration: `max_length=64`
- `state`: `CharField` — declaration: `max_length=16,choices=State.choices,default=State.PROCESSING`
- `status_code`: `PositiveSmallIntegerField` — declaration: `null=True,blank=True`
- `response_body`: `JSONField` — declaration: `null=True,blank=True`
- `expires_at`: `DateTimeField` — declaration: `db_index=True`

## How to interpret this table

- **DB NULL** describes database nullability; **Blank** describes Django validation/form optionality and is not interchangeable with NULL.
- Defaults may be callables or project helpers, so the displayed expression describes the source contract rather than a single static value.
- Relationship fields also carry deletion semantics through `on_delete`; the relation is therefore part of the lifecycle behavior of the model.
- JSON fields deliberately hold structured state/configuration; their deeper schema is documented by the owning app's contract pages.
- For inherited fields, read the model's base class before assuming a missing `id`, timestamp or permission field is absent.

## Sensitive-data rule

Credential hashes, enrollment hashes and audit metadata must not be interpreted as permission to store or document bearer token plaintext. Runtime/API documentation should describe secret handling without reproducing real credentials.
