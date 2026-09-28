# cms

## Purpose

cms owns shared Wagtail page/admin integration and presentation helpers.

## Why this boundary exists

Domain apps need one consistent Wagtail administration framework without moving their business state into a generic CMS package.

## Responsibilities

HomePage structural page; Wagtail user form/viewset configuration; reusable panels/permission helpers; hook registration.

## Non-responsibilities

Domain models remain in their owning apps. Product documentation content is docs. Deployment execution is deployments. cms has no separate REST domain API.

## Documents

- [models.md](models.md) — HomePage only.
- Domain Wagtail behavior is documented in each app README and its source wagtail_admin module.

## Security boundary

Wagtail authentication is only the outer admin gate. Domain apps retain their own rule/ownership permissions and read-only runtime fields.

## Invariants

1. cms is presentation/admin infrastructure, not business state ownership.
2. Runtime-authoritative Service/Deploy fields must not become arbitrary Wagtail form edits.
3. Product docs and engineering documentation remain separate.

## Reading order

Read the owning app README first, then its Wagtail admin module; read this app when modifying shared Wagtail behavior.
