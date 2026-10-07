# Source contract inventory

This file is the machine-checkable documentation index for first-party models and HTTP API routes.

**Generation rule:** every inventory row has a stable source signature. CI compares source declarations against these tables and fails when a model, declared field, explicit route, router registration, or router action is added/removed without updating this file.

The detailed app documentation remains the narrative contract. This file answers one narrower question: **does the documented contract inventory contain the thing that exists in source?**

## API route inventory

| App | Source | Kind | Route / prefix | Documentation |
|---|---|---|---|---|

## Router actions

| App | Source | ViewSet | Prefix | Detail | Methods | URL path |
|---|---|---|---|---|---|---|

## Model inventory

| App | Source | Model | Model kind | Documentation |
|---|---|---|---|---|
| `custom_emails` | `src/custom_emails/models.py` | `EmailTemplate` | `models.Model` | [field reference](../apps/custom_emails/field-reference.md#emailtemplate) |
| `custom_emails` | `src/custom_emails/models.py` | `EmailLog` | `models.Model` | [field reference](../apps/custom_emails/field-reference.md#emaillog) |
| `deploy` | `src/deploy/models.py` | `Deploy` | `BaseModel` | [field reference](../apps/deploy/field-reference.md#deploy) |
| `deploy` | `src/deploy/models.py` | `DeploymentResource` | `BaseModel` | [field reference](../apps/deploy/field-reference.md#deploymentresource) |
| `deploy` | `src/deploy/models.py` | `DeploymentEventOutbox` | `BaseModel` | [field reference](../apps/deploy/field-reference.md#deploymenteventoutbox) |
| `deploy` | `src/deploy/models.py` | `DeployLog` | `BaseModel` | [field reference](../apps/deploy/field-reference.md#deploylog) |
| `deploy` | `src/deploy/models.py` | `BuildCacheArtifact` | `BaseModel` | [field reference](../apps/deploy/field-reference.md#buildcacheartifact) |
| `deploy` | `src/deploy/models.py` | `BuildCacheQuota` | `BaseModel` | [field reference](../apps/deploy/field-reference.md#buildcachequota) |
| `deploy` | `src/deploy/models.py` | `BaseRuntimeImageLease` | `BaseModel` | [field reference](../apps/deploy/field-reference.md#baseruntimeimagelease) |
| `deploy` | `src/deploy/models.py` | `BaseRuntimeImage` | `BaseModel` | [field reference](../apps/deploy/field-reference.md#baseruntimeimage) |
| `deploy` | `src/deploy/models.py` | `SwarmCluster` | `BaseModel` | [field reference](../apps/deploy/field-reference.md#swarmcluster) |
| `deploy` | `src/deploy/models.py` | `SwarmNode` | `BaseModel` | [field reference](../apps/deploy/field-reference.md#swarmnode) |
| `docs` | `src/docs/models.py` | `DocumentCategory` | `models.Model` | [field reference](../apps/docs/field-reference.md#documentcategory) |
| `docs` | `src/docs/models.py` | `Document` | `models.Model` | [field reference](../apps/docs/field-reference.md#document) |
| `docs` | `src/docs/models.py` | `DocumentAsset` | `models.Model` | [field reference](../apps/docs/field-reference.md#documentasset) |
| `logs` | `src/logs/models.py` | `ServiceLogStream` | `models.Model` | [field reference](../apps/logs/field-reference.md#servicelogstream) |
| `logs` | `src/logs/models.py` | `ServiceLogEntry` | `models.Model` | [field reference](../apps/logs/field-reference.md#servicelogentry) |
| `logs` | `src/logs/models.py` | `ServiceLogUsage` | `models.Model` | [field reference](../apps/logs/field-reference.md#servicelogusage) |
| `logs` | `src/logs/models.py` | `LogUsageDaily` | `models.Model` | [field reference](../apps/logs/field-reference.md#logusagedaily) |
| `logs` | `src/logs/models.py` | `CollectorHeartbeat` | `models.Model` | [field reference](../apps/logs/field-reference.md#collectorheartbeat) |
| `messenger` | `src/messenger/models.py` | `UserBio` | `models.Model` | [field reference](../apps/messenger/field-reference.md#userbio) |
| `messenger` | `src/messenger/models.py` | `Contact` | `models.Model` | [field reference](../apps/messenger/field-reference.md#contact) |
| `messenger` | `src/messenger/models.py` | `Block` | `models.Model` | [field reference](../apps/messenger/field-reference.md#block) |
| `messenger` | `src/messenger/models.py` | `ProfilePhotoPrivacy` | `models.Model` | [field reference](../apps/messenger/field-reference.md#profilephotoprivacy) |
| `messenger` | `src/messenger/models.py` | `ProfilePhotoAllowed` | `models.Model` | [field reference](../apps/messenger/field-reference.md#profilephotoallowed) |
| `messenger` | `src/messenger/models.py` | `Conversation` | `models.Model` | [field reference](../apps/messenger/field-reference.md#conversation) |
| `messenger` | `src/messenger/models.py` | `ConversationParticipant` | `models.Model` | [field reference](../apps/messenger/field-reference.md#conversationparticipant) |
| `messenger` | `src/messenger/models.py` | `GroupInviteLink` | `models.Model` | [field reference](../apps/messenger/field-reference.md#groupinvitelink) |
| `messenger` | `src/messenger/models.py` | `JoinRequest` | `models.Model` | [field reference](../apps/messenger/field-reference.md#joinrequest) |
| `messenger` | `src/messenger/models.py` | `Message` | `models.Model` | [field reference](../apps/messenger/field-reference.md#message) |
| `messenger` | `src/messenger/models.py` | `MessengerEvent` | `models.Model` | [field reference](../apps/messenger/field-reference.md#messengerevent) |
| `messenger` | `src/messenger/models.py` | `MessageReaction` | `models.Model` | [field reference](../apps/messenger/field-reference.md#messagereaction) |
| `messenger` | `src/messenger/models.py` | `MessageReadReceipt` | `models.Model` | [field reference](../apps/messenger/field-reference.md#messagereadreceipt) |
| `messenger` | `src/messenger/models.py` | `MessageAttachment` | `models.Model` | [field reference](../apps/messenger/field-reference.md#messageattachment) |
| `messenger` | `src/messenger/models.py` | `AttachmentViewOnceOpen` | `models.Model` | [field reference](../apps/messenger/field-reference.md#attachmentviewonceopen) |
| `messenger` | `src/messenger/models.py` | `PinnedMessage` | `models.Model` | [field reference](../apps/messenger/field-reference.md#pinnedmessage) |
| `messenger` | `src/messenger/models.py` | `CallSession` | `models.Model` | [field reference](../apps/messenger/field-reference.md#callsession) |
| `messenger` | `src/messenger/models.py` | `CallSessionParticipant` | `models.Model` | [field reference](../apps/messenger/field-reference.md#callsessionparticipant) |

## Model field inventory

| App | Source | Model | Field | Django type | Documentation |
|---|---|---|---|---|---|


## Inheritance

Project-wide inherited fields are documented separately in [inherited-model-fields.md](inherited-model-fields.md). The field inventory intentionally records fields declared by each concrete/project model source; inherited framework fields are not duplicated once per model.

## Validation

Run:

```bash
python scripts/validate_documentation_contracts.py
```

Use `--check` in CI. Source code is authoritative; this inventory is intentionally strict and should be regenerated whenever routes or model declarations change.
