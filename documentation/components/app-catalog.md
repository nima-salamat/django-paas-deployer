# app_catalog

Owns catalog definitions, variants, Compose normalization, compatibility analysis and multi-service installation planning.

## API

`/api/application-catalog/apps/` exposes catalog discovery and variant resolution. Installation endpoints live under `/api/application-catalog/installations/`.

## Flow

Catalog source -> validated definition -> resolved variant -> ApplicationPlan -> Service resources -> normal deployment pipeline.

It does not create application containers directly.
