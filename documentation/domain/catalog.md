# Application Catalog

## Responsibility

`src/app_catalog/` owns declarative ready-to-deploy definitions, variants, Compose normalization, validation and multi-Service installation planning.

## Flow

```text
catalog/Compose source
 -> parse and normalize
 -> security validation
 -> variables/secrets
 -> ApplicationPlan
 -> Service + ServiceProcess + endpoints/volumes/secrets
 -> normal revision/runtime pipeline
```

The catalog is an input/planning layer, not a second runtime engine.

## Security

Unsupported Compose semantics fail closed. Privileged mode, host networking, unsafe mounts, device/capability escape routes and unsupported host publication are not silently approximated.

## External catalogs

`APP_CATALOG_SOURCE_DIRS` can load additional YAML/Compose trees after validation.

## Compatibility analysis

The compatibility analyzer reports parser/planner support, unsupported features, warnings and selection eligibility without deploying anything.
