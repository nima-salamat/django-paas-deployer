# core background behavior

core provides infrastructure rather than a domain lifecycle.

System settings are loaded through settings_service typed accessors. app_cache uses namespaced keys and explicit invalidation functions; cache misses must fall back to durable data.

core/tasks/email.py provides shared asynchronous email helper behavior used by authentication/other flows. core/tasks/zip_utils.py provides archive safety/utility paths.

Wagtail/cache admin views expose operator diagnostics. These views must not turn cache contents into an authoritative data source.

## Tests as contracts

test_throttling.py protects request-rate controls. test_wagtail_cache_admin.py and tests_production_admin.py protect operator/admin boundaries and cache diagnostics.
