# custom_emails models

This is the canonical model contract for custom_emails. Field tables describe the current Django declarations; model notes explain architectural meaning beyond ORM metadata.

## EmailTemplate

Admin-managed source template. Updating it affects future renderings, not historical completed EmailLog entries.

Base: models.Model

| Field | Django type | Null / default / key metadata | Architectural meaning, writers/readers and authority |
|---|---|---|---|
| name | CharField | \\|n\\|u\\|l\\|l\\|=\\|F\\|a\\|l\\|s\\|e\\|;\\| \\|d\\|e\\|f\\|a\\|u\\|l\\|t\\|=\\|n\\|o\\|n\\|e\\|;\\| \\|u\\|n\\|i\\|q\\|u\\|e\\| | Human-facing/domain identifier text. Written through the app's validated API/admin paths and read by UI/search; uniqueness/normalization rules must be preserved. |
| subject | CharField | \\|n\\|u\\|l\\|l\\|=\\|F\\|a\\|l\\|s\\|e\\|;\\| \\|d\\|e\\|f\\|a\\|u\\|l\\|t\\|=\\|n\\|o\\|n\\|e\\| | Domain data field owned by this model. The app's create/update workflow is responsible for writing it; callers should use the documented API/model operation rather than assuming direct mutation is safe. |
| body | TextField | \\|n\\|u\\|l\\|l\\|=\\|F\\|a\\|l\\|s\\|e\\|;\\| \\|d\\|e\\|f\\|a\\|u\\|l\\|t\\|=\\|n\\|o\\|n\\|e\\| | Domain data field owned by this model. The app's create/update workflow is responsible for writing it; callers should use the documented API/model operation rather than assuming direct mutation is safe. |
| description | TextField | \\|n\\|u\\|l\\|l\\|=\\|F\\|a\\|l\\|s\\|e\\|;\\| \\|b\\|l\\|a\\|n\\|k\\|=\\|T\\|r\\|u\\|e\\|;\\| \\|d\\|e\\|f\\|a\\|u\\|l\\|t\\|=\\|"\\|"\\| | Human-facing/domain identifier text. Written through the app's validated API/admin paths and read by UI/search; uniqueness/normalization rules must be preserved. |
| is_active | BooleanField | \\|n\\|u\\|l\\|l\\|=\\|F\\|a\\|l\\|s\\|e\\|;\\| \\|d\\|e\\|f\\|a\\|u\\|l\\|t\\|=\\|T\\|r\\|u\\|e\\| | Boolean policy/state flag. Written by the owning workflow or admin boundary; consumers use it as authorization or lifecycle state, not as a substitute for an independent state machine. |
| created_by | ForeignKey | \\|n\\|u\\|l\\|l\\|=\\|T\\|r\\|u\\|e\\|;\\| \\|b\\|l\\|a\\|n\\|k\\|=\\|T\\|r\\|u\\|e\\|;\\| \\|d\\|e\\|f\\|a\\|u\\|l\\|t\\|=\\|n\\|o\\|n\\|e\\|;\\| \\|r\\|e\\|l\\|a\\|t\\|e\\|s\\| \\|t\\|o\\| \\|r\\|e\\|l\\|a\\|t\\|i\\|o\\|n\\| | Domain data field owned by this model. The app's create/update workflow is responsible for writing it; callers should use the documented API/model operation rather than assuming direct mutation is safe. |
| created_at | DateTimeField | \\|n\\|u\\|l\\|l\\|=\\|F\\|a\\|l\\|s\\|e\\|;\\| \\|d\\|e\\|f\\|a\\|u\\|l\\|t\\|=\\|n\\|o\\|n\\|e\\| | Lifecycle/audit time. Normally written by the owning model/workflow and read for ordering, expiry or history; a future change must preserve timezone/meaning. |
| updated_at | DateTimeField | \\|n\\|u\\|l\\|l\\|=\\|F\\|a\\|l\\|s\\|e\\|;\\| \\|d\\|e\\|f\\|a\\|u\\|l\\|t\\|=\\|n\\|o\\|n\\|e\\| | Lifecycle/audit time. Normally written by the owning model/workflow and read for ordering, expiry or history; a future change must preserve timezone/meaning. |

## EmailLog

One delivery intent/result record. HTTP creates it; Celery owns the external delivery transition. celery_task_id identifies worker execution.

Base: models.Model

| Field | Django type | Null / default / key metadata | Architectural meaning, writers/readers and authority |
|---|---|---|---|
| recipient | ForeignKey | \\|n\\|u\\|l\\|l\\|=\\|T\\|r\\|u\\|e\\|;\\| \\|b\\|l\\|a\\|n\\|k\\|=\\|T\\|r\\|u\\|e\\|;\\| \\|d\\|e\\|f\\|a\\|u\\|l\\|t\\|=\\|n\\|o\\|n\\|e\\|;\\| \\|r\\|e\\|l\\|a\\|t\\|e\\|s\\| \\|t\\|o\\| \\|r\\|e\\|l\\|a\\|t\\|i\\|o\\|n\\| | Domain data field owned by this model. The app's create/update workflow is responsible for writing it; callers should use the documented API/model operation rather than assuming direct mutation is safe. |
| recipient_email | EmailField | \\|n\\|u\\|l\\|l\\|=\\|F\\|a\\|l\\|s\\|e\\|;\\| \\|d\\|e\\|f\\|a\\|u\\|l\\|t\\|=\\|n\\|o\\|n\\|e\\| | Domain data field owned by this model. The app's create/update workflow is responsible for writing it; callers should use the documented API/model operation rather than assuming direct mutation is safe. |
| template | ForeignKey | \\|n\\|u\\|l\\|l\\|=\\|T\\|r\\|u\\|e\\|;\\| \\|b\\|l\\|a\\|n\\|k\\|=\\|T\\|r\\|u\\|e\\|;\\| \\|d\\|e\\|f\\|a\\|u\\|l\\|t\\|=\\|n\\|o\\|n\\|e\\|;\\| \\|r\\|e\\|l\\|a\\|t\\|e\\|s\\| \\|t\\|o\\| \\|r\\|e\\|l\\|a\\|t\\|i\\|o\\|n\\| | Domain data field owned by this model. The app's create/update workflow is responsible for writing it; callers should use the documented API/model operation rather than assuming direct mutation is safe. |
| subject | CharField | \\|n\\|u\\|l\\|l\\|=\\|F\\|a\\|l\\|s\\|e\\|;\\| \\|d\\|e\\|f\\|a\\|u\\|l\\|t\\|=\\|n\\|o\\|n\\|e\\| | Domain data field owned by this model. The app's create/update workflow is responsible for writing it; callers should use the documented API/model operation rather than assuming direct mutation is safe. |
| body_preview | TextField | \\|n\\|u\\|l\\|l\\|=\\|F\\|a\\|l\\|s\\|e\\|;\\| \\|b\\|l\\|a\\|n\\|k\\|=\\|T\\|r\\|u\\|e\\|;\\| \\|d\\|e\\|f\\|a\\|u\\|l\\|t\\|=\\|"\\|"\\| | Domain data field owned by this model. The app's create/update workflow is responsible for writing it; callers should use the documented API/model operation rather than assuming direct mutation is safe. |
| status | CharField | \\|n\\|u\\|l\\|l\\|=\\|F\\|a\\|l\\|s\\|e\\|;\\| \\|d\\|e\\|f\\|a\\|u\\|l\\|t\\|=\\|S\\|t\\|a\\|t\\|u\\|s\\|.\\|P\\|E\\|N\\|D\\|I\\|N\\|G\\|;\\| \\|i\\|n\\|d\\|e\\|x\\|e\\|d\\| | State-machine field. The owning workflow defines legal transitions; readers use the value to decide which operations are safe. |
| error_message | TextField | \\|n\\|u\\|l\\|l\\|=\\|F\\|a\\|l\\|s\\|e\\|;\\| \\|b\\|l\\|a\\|n\\|k\\|=\\|T\\|r\\|u\\|e\\|;\\| \\|d\\|e\\|f\\|a\\|u\\|l\\|t\\|=\\|"\\|"\\| | Domain data field owned by this model. The app's create/update workflow is responsible for writing it; callers should use the documented API/model operation rather than assuming direct mutation is safe. |
| sent_by | ForeignKey | \\|n\\|u\\|l\\|l\\|=\\|T\\|r\\|u\\|e\\|;\\| \\|b\\|l\\|a\\|n\\|k\\|=\\|T\\|r\\|u\\|e\\|;\\| \\|d\\|e\\|f\\|a\\|u\\|l\\|t\\|=\\|n\\|o\\|n\\|e\\|;\\| \\|r\\|e\\|l\\|a\\|t\\|e\\|s\\| \\|t\\|o\\| \\|r\\|e\\|l\\|a\\|t\\|i\\|o\\|n\\| | Domain data field owned by this model. The app's create/update workflow is responsible for writing it; callers should use the documented API/model operation rather than assuming direct mutation is safe. |
| is_test | BooleanField | \\|n\\|u\\|l\\|l\\|=\\|F\\|a\\|l\\|s\\|e\\|;\\| \\|d\\|e\\|f\\|a\\|u\\|l\\|t\\|=\\|F\\|a\\|l\\|s\\|e\\| | Boolean policy/state flag. Written by the owning workflow or admin boundary; consumers use it as authorization or lifecycle state, not as a substitute for an independent state machine. |
| created_at | DateTimeField | \\|n\\|u\\|l\\|l\\|=\\|F\\|a\\|l\\|s\\|e\\|;\\| \\|d\\|e\\|f\\|a\\|u\\|l\\|t\\|=\\|n\\|o\\|n\\|e\\|;\\| \\|i\\|n\\|d\\|e\\|x\\|e\\|d\\| | Lifecycle/audit time. Normally written by the owning model/workflow and read for ordering, expiry or history; a future change must preserve timezone/meaning. |
| sent_at | DateTimeField | \\|n\\|u\\|l\\|l\\|=\\|T\\|r\\|u\\|e\\|;\\| \\|b\\|l\\|a\\|n\\|k\\|=\\|T\\|r\\|u\\|e\\|;\\| \\|d\\|e\\|f\\|a\\|u\\|l\\|t\\|=\\|n\\|o\\|n\\|e\\| | Lifecycle/audit time. Normally written by the owning model/workflow and read for ordering, expiry or history; a future change must preserve timezone/meaning. |
| failed_at | DateTimeField | \\|n\\|u\\|l\\|l\\|=\\|T\\|r\\|u\\|e\\|;\\| \\|b\\|l\\|a\\|n\\|k\\|=\\|T\\|r\\|u\\|e\\|;\\| \\|d\\|e\\|f\\|a\\|u\\|l\\|t\\|=\\|n\\|o\\|n\\|e\\| | Lifecycle/audit time. Normally written by the owning model/workflow and read for ordering, expiry or history; a future change must preserve timezone/meaning. |
| celery_task_id | CharField | \\|n\\|u\\|l\\|l\\|=\\|F\\|a\\|l\\|s\\|e\\|;\\| \\|b\\|l\\|a\\|n\\|k\\|=\\|T\\|r\\|u\\|e\\|;\\| \\|d\\|e\\|f\\|a\\|u\\|l\\|t\\|=\\|"\\|"\\| | Domain data field owned by this model. The app's create/update workflow is responsible for writing it; callers should use the documented API/model operation rather than assuming direct mutation is safe. |

## State, deletion and maintenance rules

The source model definitions call full_clean() on several important saves and define database constraints/indexes in Meta. Deletion behavior is part of the domain contract: read the on_delete declarations above together with the app README before changing cascades, SET_NULL, PROTECT or replacement semantics.

JSON fields are structured contracts. Do not introduce keys by observation from one API response; update the producer, consumer and serializer contract together. Sensitive JSON values are security state and must be redacted or encrypted according to the app rules.

## Implementation versus intent

**Current implementation:** the tables reflect the current master branch model declarations and call-site semantics.

**Architectural intent:** models store durable domain state; runtime observations and transient worker state are separated where the architecture requires it.

**Compatibility behavior:** fields explicitly described as projections, legacy state, or migration bridges must not be interpreted as a second source of truth.

**Do not assume:** a Django field being writable at the ORM level means any API or worker is allowed to mutate it. Workflow ownership and invariants in the app documentation control safe writes.
