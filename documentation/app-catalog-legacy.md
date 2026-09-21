# Ready-to-Deploy Catalog Notes

Bundled catalog definitions live under `src/app_catalog/catalog/`. Additional catalog roots can be supplied through `APP_CATALOG_SOURCE_DIRS`.

Compose is an input representation. Definitions are parsed, security-validated, normalized, resolved into configuration/secrets and then converted into ordinary Service-domain resources.

Generated secrets become ServiceSecret versions. Catalog definitions store definition/software version metadata so later catalog changes do not silently rewrite existing installations.

Direct host exposure and other unsupported Compose features are rejected rather than silently translated.
