# Agent documentation and source lookup

`scripts/agent_docs.py` is a repository-local, standard-library-only lookup tool for coding agents. It searches the engineering documentation and a static index of source declarations. It is deliberately offline: it does not need Django settings, a database, Redis, a running web server, a GitHub token or third-party packages.

## Quick start

Run from any working directory in the checkout:

```bash
python scripts/agent_docs.py search ServiceRevision --kind model --json
python scripts/agent_docs.py search "/agent/v1/services/{service_id}/rebuild" --kind api --json
python scripts/agent_docs.py search "runtime reconciliation" --kind system
python scripts/agent_docs.py search "database credentials" --app agent --limit 10
python scripts/agent_docs.py audit --json
```

The command resolves the repository root from the script's own location, so the current working directory does not affect where it searches.

## Search kinds

| Kind | Indexed material | Example |
|---|---|---|
| `model` | Sections of model/field-reference documentation and Django model classes declared in `src/**/models.py` | `search ServiceRevision --kind model` |
| `api` | App API guides, API contract docs, literal `path()`/`re_path()` routes and DRF router registrations | `search "/agent/v1/services/{service_id}/rebuild" --kind api` |
| `system` | Architecture, execution, background, invariant and state-contract documentation | `search "worker recovery" --kind system` |
| `all` | All indexed material | `search "database credentials"` |

`--app` restricts results to one first-party app name such as `services`, `deploy` or `agent`. `--limit` bounds the number of results (default 8). `--json` returns a structured response suitable for scripts and LLM tool adapters.

## Result contract

Each result contains:

| Field | Meaning |
|---|---|
| `kind` | `model`, `api`, `system` or the document's general classification |
| `title` | Model name, documentation heading or HTTP method/route |
| `path` | Repository-relative documentation or source path |
| `line` | Markdown heading or Python declaration/route line when available |
| `summary` | Relevant section text, model docstring/declared field names, or route handler hint |
| `app` | Owning Django app when it can be determined |
| `source` | True when the result points to a source declaration rather than a Markdown section |
| `score` | Approximate title/path/body relevance score; it is ranking only, not confidence or authority |

For an API result, open the referenced API guide to understand required path/query/body parameters, authentication, scopes, object ownership, side effects, asynchronous completion and failure behavior. The source route row only identifies the URL declaration and view handler; it is not a substitute for that behavioral contract.

For a model result, open the owning app's `models.md` for domain meaning and `field-reference.md` for field-level details. The source entry is useful to confirm the current class and declaration location.

## Coverage audit

`python scripts/agent_docs.py audit` compares top-level model classes detected in the source with explicit section headings in each app's `models.md`. A model mention buried in another model's paragraph or a field table does not count as a model explanation. It also checks that URL-owning apps have an app-level `api.md` or `api-reference.md`.

The JSON audit includes:
- `models_discovered` and per-app `model_coverage`
- `models_missing_from_docs`
- `static_routes_discovered` and `apps_with_routes`
- `apps_without_api_guide`
- `notes` describing static-analysis limitations

Exit code is zero when the detected model names and API guide-presence checks have no gaps; otherwise it is non-zero. A passing audit does not prove every endpoint's payload, permission or behavior is documented.

## Static-analysis limits and authority

The index is intentionally dependency-free, but it is not a replacement for Django's URL resolver or a runtime OpenAPI schema:

- It reads literal route patterns from `path()` and `re_path()`, detects `include()` prefixes in `src/config/urls.py`, and identifies basic `router.register()` collection/detail routes.
- It does not execute URL modules. Routes assembled dynamically, custom DRF actions, decorator-generated routes, Wagtail routes, middleware paths and routes registered outside scanned URL modules may not be completely represented.
- Model discovery scans top-level Django model classes in the primary `models.py` modules. It does not attempt to migrate the database or inspect third-party, dynamically generated or Wagtail admin extension models.
- The search score is heuristic. A high score does not imply permission to call an endpoint or confidence that the first result is the complete answer.
- The audit tests model-name coverage and API-guide presence. It does not semantically compare every request schema and response example.

Use these sources in this order when changing behavior:

1. Owning app implementation, serializers, permissions and tests.
2. Owning app `api.md`/`api-reference.md`, `models.md`, `field-reference.md` and state/background docs.
3. [Source contract inventory](contracts.md) and [documentation completeness manifest](documentation-completeness.md).
4. This CLI index as a navigation aid.

Also run the repository's more detailed static inventory parity checker:

```bash
python scripts/validate_documentation_contracts.py
```

That checker compares the centralized `contracts.md` inventory against source API routes, DRF router registrations/actions, models and fields. Keep both checks updated when code and contracts change.

## Agent workflow

Before editing a feature:
1. Search by the endpoint path, model/class name, error code or system concept.
2. Open the owning app guide and source file from the returned paths.
3. Read the relevant tests and permission/serializer implementation before proposing a change.
4. After editing, update the app-level contract and the central inventory.
5. Run both documentation checkers and the feature tests; report separately what actually passed.

Do not infer authorization from a search result. Agent API scopes and the underlying user/share permission checks remain the only access contract.
