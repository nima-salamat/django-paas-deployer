# users models

## User

The custom AUTH_USER_MODEL. It is the durable identity referenced by all user-owned domains.

| Field | Type / null / default | Why it exists and authority |
|---|---|---|
| uuid | CharField(32), unique, generated, non-editable | Stable external-friendly identity. Model-generated; consumers must not replace it with login/session ids. |
| username | CharField(32), unique | Canonical login/display identifier. Written at account creation or account-level update; auth_users resolves credentials against it. |
| first_name | CharField(150), blank/default "" | Wagtail/identity presentation compatibility. Not authentication state. |
| last_name | CharField(150), blank/default "" | Identity presentation compatibility. |
| password | CharField(128), nullable/blank | Django password hash storage. Password presence is derived with has_usable_password(); auth flows own policy. |
| email | EmailField(255), nullable/blank/unique | Durable contact identity. Contact changes must use auth_users verification; normal User update rejects direct change. |
| email_verified | Boolean, default false | Verification state for email. Written by verified auth/contact flows. |
| phone_number | PhoneNumberField, nullable/blank/unique | Durable phone contact. Updated through auth_users contact verification. |
| phone_number_verified | Boolean, default false | Phone verification state; not proof of current login. |
| theme | CharField(7), choices light/dark, default light | User UI preference. Not an authorization or runtime policy. |
| color | PositiveSmallIntegerField, COLOR_CHOICES | Stable profile color used by UI. |
| birthdate | DateField, nullable/blank | Optional account profile data. |
| balance | DecimalField(11,3), default 0 | Account credit balance. Receipt.change_balance() is the transactional mutation path. |
| is_staff | Boolean, default false | Wagtail/Django operator access flag; protected by admin/permission layers. |
| is_active | Boolean, default true | Account usability. Deactivation is preferred over deletion for ordinary account disabling. |
| date_joined | DateTimeField, default timezone.now | Account creation timestamp. |
| national_id | CharField(11), nullable/blank | Optional regulated identity data. Sensitive; do not expose casually. |

Authentication/session state belongs to auth_users, so adding session policy fields to User is an architectural boundary change.

## Receipt

A user-linked payment/accounting record.

| Field | Type | Semantics |
|---|---|---|
| user | FK User, CASCADE | Owner of the receipt. |
| amount | Decimal(11,3) | Amount to credit/debit according to payment workflow. |
| created_at | DateTime | Creation audit time. |
| updated_at | DateTime | Last mutation time. |
| status | PaymentChoices | NOT_PAYED, PAYED or CANCELED. Payment state is not the same as User.balance. |

Receipt.change_balance() runs in a transaction, updates the User balance and marks the receipt paid. A future payment feature should use that operation or an equivalent atomic accounting service rather than incrementing balance directly.

## Profile

A user may have multiple profile images.

| Field | Type | Semantics |
|---|---|---|
| order | Integer, default 0 | Presentation ordering; Profile APIs explicitly rewrite it. |
| user | FK User, CASCADE | Owner and authorization scope. |
| image | ImageField, validated, max 2 MB and 2560x1440 | Profile asset; users owns storage and cleanup. |
| created_at | DateTime | Creation ordering/audit. |

Model validation caps a user at five profiles.

## Rule

One-to-one application permission catalog.

| Field | Type | Semantics |
|---|---|---|
| user | OneToOne User, CASCADE | Permission subject. |
| rules | PostgreSQL ArrayField(CharField(100)), default list | Structured permission codes such as services.manage or docs.manage. Admin APIs read it to determine application capability; it is not a general Django Group replacement. |
| updated_at | DateTime | Audit. |
| created_at | DateTime | Creation audit. |

The ArrayField is structured, not arbitrary JSON: values are string permission codes. Superusers bypass many app rule checks; staff rules are enforced by the owning API.

## PermissionMixin

Abstract base used by User. is_superuser is the Django permission flag, and has_perm() additionally respects active/superuser semantics implemented by the project.

## Deletion semantics and implicit state

User deletion cascades identity-owned rows but also triggers `users.signals.cleanup_user_resources`. The signal fences owned Service lifecycle generations, prepares network attachment rows for safe collector ordering, and relies on Service/Volume/PrivateNetwork signals for Docker ownership cleanup. Messenger applies group/DM leave semantics separately, while catalog hard deletion removes protected child bindings before the User collector runs.

Audit/history records intentionally linked with `SET_NULL` survive account deletion where the owning app defines them as durable audit history (for example auth LoginLog and agent audit events). Cross-database service logs are removed by the Service deletion boundary rather than by the primary User FK cascade.

Do not use direct raw SQL deletion of User without reproducing these side effects and their ordering contracts.

## Architecturally meaningful migrations

- 0003 added balance, national_id and profile-image constraints/changes.
- 0004 restored groups/permissions compatibility.
- 0005 changed superuser behavior.
These migrations are evidence of compatibility with Django/Wagtail administration rather than a separate identity architecture.

## Current implementation / intent / compatibility

Current implementation: User is the custom Django auth model and is referenced throughout the product.

Architectural intent: durable identity remains independent of session/credential protocol state.

Compatibility behavior: first_name/last_name, Django permissions and Wagtail admin fields remain for framework compatibility.
