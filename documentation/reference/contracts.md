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
