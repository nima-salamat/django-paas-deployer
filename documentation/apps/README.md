# Django application architecture map

This directory is the canonical architectural index for the fourteen first-party Django applications installed by src/config/settings.py. It is more implementation-aware than the system overview in ../architecture.md.

## Canonical application set

| App | Architectural responsibility | Source |
|---|---|---|
| users | Identity, profiles, roles, balance and profile assets | src/users/ |
| auth_users | Authentication protocol, OTP/recovery, devices and sessions | src/auth_users/ |
| services | Durable workload domain and desired executable state | src/services/ |
| plans | Resource, storage, logging and pricing policy envelope | src/plans/ |
| deploy | Deployment records, deploy logs, base-image registry and Swarm metadata | src/deploy/ |
| deployments | Planning, build, runtime, lifecycle, reconciliation | src/deployments/ |
| logs | Runtime service-log ingestion, persistence and retention | src/logs/ |
| app_catalog | Catalog definitions and multi-service installation coordination | src/app_catalog/ |
| messenger | Conversations, membership, messages, media and calls | src/messenger/ |
| tickets | Customer support workflow | src/tickets/ |
| custom_emails | Admin-managed email templates and asynchronous delivery | src/custom_emails/ |
| docs | Product documentation content and media | src/docs/ |
| core | Shared settings, cache, protected media and infrastructure helpers | src/core/ |
| cms | Wagtail page/admin integration | src/cms/ |

src/config/, src/static/, src/templates/ and root documentation/ are not first-party Django application boundaries.

## Cross-app interaction map

~~~text
users
├── auth_users        identity consumed by authentication state
├── services          ownership and actor identity
├── deploy            deployment creator identity
├── messenger         participants and profiles
├── tickets           ticket owners/staff
├── custom_emails     recipients and senders
├── app_catalog       installation owner
└── cms               Wagtail forms/admin

auth_users
├── users             canonical identity
├── core              settings/cache/email infrastructure
└── custom_emails/core.tasks
                       OTP notification plumbing

plans
└── services          Service.plan carries the customer policy envelope

services
├── plans             quota and plan policy
├── users             ownership/actors
├── messenger         group-based ServiceShare targets
├── deploy            Deploy relationship and compatibility projection
├── deployments       planning/execution
├── logs              service-log access and correlation
└── core              settings/cache/shared infrastructure

app_catalog
├── users             installation owner
├── plans             plan validation
├── services          creates child services
├── deploy            child Deploy records
└── deployments       children use the normal deployment pipeline

messenger
├── users             identity/profile
├── services          ServiceShare group target and cleanup
├── core              protected media
└── Channels/Redis/Celery
                     realtime, cache and scheduled delivery

tickets
├── users             identity and staff scope
├── services/deploy   optional support context
├── core              settings/cache
└── Channels          realtime notifications

custom_emails
├── users             recipients/admin actors
├── tickets           rate-limit helper
├── core              Resend proxy configuration
└── Celery             asynchronous delivery

docs
├── auth_users         auth/permission policy
└── core               file serving policy

core
├── auth_users         authentication adapters
├── deploy/deployments system/runtime adapters
└── major apps         shared settings/cache/admin surfaces

cms
├── users              custom Wagtail user forms
└── app-level hooks    Wagtail snippet administration
~~~

## Authority map

| Concept | Source of truth |
|---|---|
| User identity | users.User |
| Session validity | auth_users.UserSession plus session checks |
| Service desired lifecycle | services.Service.desired_state |
| Current executable service release | services.Service.active_revision |
| Historical deployment attempt | deploy.Deploy |
| Compatibility deploy projection | services.Service.selected_deploy |
| Executable snapshot | services.ServiceRevision |
| Runtime truth | Docker/Swarm observations consumed by deployments |
| Runtime service logs | logs |
| Deployment lifecycle events | deploy.DeployLog |
| Plan policy | plans.Plan plus operator settings |
| Catalog installation coordinator | app_catalog.ApplicationInstance |
| Durable messenger event metadata | messenger.MessengerEvent |
| Product docs | docs.Document |

## Boundary rules

Identity and authentication are separate. users owns what the account is; auth_users owns how credentials and sessions are validated.

services owns desired workload state and revision snapshots. deployments owns execution and runtime orchestration. deploy persists execution/provenance and infrastructure registry state but is not a second runtime engine.

logs and deploy.DeployLog are separate event systems even though both are called logs.

src/docs is product CMS data; root documentation is engineering architecture memory.

## Problem navigation

| Problem | Start here | Then inspect |
|---|---|---|
| Login/session failure | auth_users/README.md | users, authentication/session tests |
| Resource access leak | resource app API docs | users/share permissions/serializer |
| Service field accepted but runtime ignores it | services/README.md | deployments/02-request-to-plan.md and revisioning |
| Wrong deployment activation | deploy/README.md | deployments/03-execution-lifecycle.md and services/revisioning |
| Unexpected base-image rebuild | deploy/README.md | deployments/08-base-images.md |
| Missing runtime logs | logs/README.md | services runtime-log API and collector |
| Missing deployment logs | deploy/README.md | deployments/09-logs-health-rollback-cleanup.md |
| Secret masking failure | app serializers.md | permission helper and sensitive model |
| Messenger realtime mismatch | messenger/README.md | messenger/background.md |
| Catalog installation stuck | app_catalog/README.md | coordinator tasks and child Deploy |
| Ticket visibility bug | tickets/README.md | permissions, queryset and serializers |

## Reading order

Read ../architecture.md, then this map, then the relevant app README. For deployment work also read ../deployments/README.md before opening src/deployments/.

## Implementation versus intent

Current implementation: several compatibility bridges and deliberate cross-app helpers remain.

Architectural intent: domain state stays with its owning app while execution/runtime coordination is centralized under deployments.

Compatibility behavior: legacy routes, selected_deploy and compatibility facades remain supported.

Do not assume: package names alone prove that every production path uses the newest abstraction.
