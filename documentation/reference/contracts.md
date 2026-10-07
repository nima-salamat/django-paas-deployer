# Source contract inventory

This document is the canonical machine-checkable inventory for first-party models, declared model fields, API routes, and DRF router registrations.

Source code is authoritative. App-level API/model references explain behavior; this file provides stable source signatures so CI can detect documentation drift.

## API route inventory

| App | Source | Kind | Route / prefix | Documentation |
|---|---|---|---|---|

## Router actions

| App | Source | ViewSet | Prefix | Detail | Methods | URL path | Kind |
|---|---|---|---|---|---|---|---|

## Model inventory

| App | Source | Model | Model kind | Documentation |
|---|---|---|---|---|

## Model field inventory

| App | Source | Model | Field | Django type | Documentation |
|---|---|---|---|---|---|

## Inheritance

See [inherited-model-fields.md](inherited-model-fields.md) for project-wide BaseModel fields and framework/Wagtail inheritance boundaries.

## Validation

Run `python scripts/validate_documentation_contracts.py`.

CI must fail when source contains a model, declared field, explicit API route, router registration, or registered route surface that is missing from this inventory, or when a stale inventory row remains after source deletion.
