# cms models

## HomePage

Wagtail root page used as the structural site homepage.

| Field | Type | Semantics |
|---|---|---|
| body | RichTextField, blank/default "" | Minimal editable homepage content. It is CMS presentation data, not the source of product documentation or platform runtime state. |

Wagtail Page already supplies page identity/tree fields. HomePage intentionally has no allowed subpage types in the current implementation; the project uses API-first/domain-specific screens rather than a deep Wagtail page tree.

Deletion follows Wagtail Page semantics. Do not move Service/Deploy business state into this model merely because it is editable from Wagtail.

Source: src/cms/models.py.

> **Complete field reference:** [field-reference.md](field-reference.md) lists every field explicitly declared in `src/cms/models.py`, including type, null/blank behavior, defaults, constraints and purpose.
