# core — complete model field reference

Source-derived from `src/core/models.py` on `master`. This supplements [models.md](models.md) with a field-by-field persistence and validation reference. Only fields explicitly declared by this source file are listed; fields inherited from Django or project base classes are noted in the inheritance section.

## SystemSetting

**Bases:** `models.Model`  
**Declared fields:** 10

| Field | Type | DB NULL | Blank | Default | Constraints | Purpose / why it exists |
|---|---|---:|---:|---|---|---|
| `key` | `CharField` | no | no | `—` | DB non-null, blank not allowed, unique, indexed | Stable configuration/lookup key. |
| `value` | `TextField` | no | yes | `""` | DB non-null, blank allowed | Stored value for the owning configuration contract. |
| `value_type` | `CharField` | no | no | `SettingValueType.STRING` | DB non-null, blank not allowed, choices; choices | Stores the value type required by the SystemSetting contract. |
| `category` | `CharField` | no | no | `SettingCategory.GENERAL` | DB non-null, blank not allowed, indexed, choices; choices | Stores the category required by the SystemSetting contract. |
| `label` | `CharField` | no | yes | `""` | DB non-null, blank allowed | Stores the label required by the SystemSetting contract. |
| `description` | `TextField` | no | yes | `""` | DB non-null, blank allowed | Human-readable explanation or metadata. |
| `is_secret` | `BooleanField` | no | no | `False` | DB non-null, blank not allowed | Stores the is secret required by the SystemSetting contract. |
| `is_editable` | `BooleanField` | no | no | `True` | DB non-null, blank not allowed | Stores the is editable required by the SystemSetting contract. |
| `updated_at` | `DateTimeField` | no | no | `—` | DB non-null, blank not allowed | Last-update timestamp for ordering, cache and reconciliation decisions. |
| `created_at` | `DateTimeField` | no | no | `—` | DB non-null, blank not allowed | Creation timestamp for history and ordering. |

### Declaration details

- `key`: `CharField` — declaration: `_("Key"), max_length=128, unique=True, db_index=True, help_text=_("Stable machine key, e.g. mirror.python or build.max_cpu"),`
- `value`: `TextField` — declaration: `_("Value"), blank=True, default="", help_text=_("Stored as text; cast using value_type."),`
- `value_type`: `CharField` — declaration: `_("Value type"), max_length=16, choices=SettingValueType.choices, default=SettingValueType.STRING,`
- `category`: `CharField` — declaration: `_("Category"), max_length=32, choices=SettingCategory.choices, default=SettingCategory.GENERAL, db_index=True,`
- `label`: `CharField` — declaration: `_("Label"), max_length=128, blank=True, default=""`
- `description`: `TextField` — declaration: `_("Description"), blank=True, default=""`
- `is_secret`: `BooleanField` — declaration: `_("Secret"), default=False, help_text=_("Hide raw value in non-staff API responses."),`
- `is_editable`: `BooleanField` — declaration: `_("Editable"), default=True, help_text=_("If false, admin/API cannot change this key."),`
- `updated_at`: `DateTimeField` — declaration: `auto_now=True`
- `created_at`: `DateTimeField` — declaration: `auto_now_add=True`

## CoreSettings

**Bases:** `BaseGenericSetting`  
**Declared fields:** 44

| Field | Type | DB NULL | Blank | Default | Constraints | Purpose / why it exists |
|---|---|---:|---:|---|---|---|
| `base_images_enabled` | `BooleanField` | no | no | `True` | DB non-null, blank not allowed | Stores the base images enabled required by the CoreSettings contract. |
| `base_images_auto_build` | `BooleanField` | no | no | `True` | DB non-null, blank not allowed | Stores the base images auto build required by the CoreSettings contract. |
| `base_images_retain_after_deploy` | `BooleanField` | no | no | `True` | DB non-null, blank not allowed | Deployment relationship used for execution/provenance correlation. |
| `base_image_build_timeout_minutes` | `PositiveIntegerField` | no | no | `10` | DB non-null, blank not allowed; validators | Stores the base image build timeout minutes required by the CoreSettings contract. |
| `base_images_auto_register_existing` | `BooleanField` | no | no | `True` | DB non-null, blank not allowed | Stores the base images auto register existing required by the CoreSettings contract. |
| `auto_public_url_handling` | `BooleanField` | no | no | `True` | DB non-null, blank not allowed | Stores the auto public url handling required by the CoreSettings contract. |
| `default_public_url_prefix` | `CharField` | no | yes | `""` | DB non-null, blank allowed | Stores the default public url prefix required by the CoreSettings contract. |
| `mirror_docker` | `CharField` | no | no | `"docker.arvancloud.ir"` | DB non-null, blank not allowed | Stores the mirror docker required by the CoreSettings contract. |
| `mirror_python` | `CharField` | no | no | `"https://mirror-pypi.runflare.com/simple"` | DB non-null, blank not allowed | Stores the mirror python required by the CoreSettings contract. |
| `mirror_npm` | `CharField` | no | no | `"https://package-mirror.liara.ir/repository/npm/"` | DB non-null, blank not allowed | Stores the mirror npm required by the CoreSettings contract. |
| `mirror_composer` | `CharField` | no | no | `"https://package-mirror.liara.ir/repository/composer/"` | DB non-null, blank not allowed | Stores the mirror composer required by the CoreSettings contract. |
| `mirror_apt` | `CharField` | no | no | `"http://repo.iut.ac.ir/debian/"` | DB non-null, blank not allowed | Stores the mirror apt required by the CoreSettings contract. |
| `mirror_go` | `CharField` | no | yes | `""` | DB non-null, blank allowed | Stores the mirror go required by the CoreSettings contract. |
| `build_resource_mode` | `CharField` | no | no | `"static"` | DB non-null, blank not allowed, choices; choices | Stores the build resource mode required by the CoreSettings contract. |
| `build_pids_limit` | `PositiveIntegerField` | no | no | `2048` | DB non-null, blank not allowed | Stores the build pids limit required by the CoreSettings contract. |
| `build_shm_mb` | `PositiveIntegerField` | no | no | `64` | DB non-null, blank not allowed | Stores the build shm mb required by the CoreSettings contract. |
| `build_parallelism` | `PositiveSmallIntegerField` | no | no | `1` | DB non-null, blank not allowed | Stores the build parallelism required by the CoreSettings contract. |
| `build_wait_minutes` | `PositiveSmallIntegerField` | no | no | `5` | DB non-null, blank not allowed | Stores the build wait minutes required by the CoreSettings contract. |
| `build_max_cpu` | `FloatField` | no | no | `1.0` | DB non-null, blank not allowed | Stores the build max cpu required by the CoreSettings contract. |
| `build_max_ram_mb` | `PositiveIntegerField` | no | no | `1024` | DB non-null, blank not allowed | Stores the build max ram mb required by the CoreSettings contract. |
| `volume_usage_warning_percent` | `FloatField` | no | no | `90.0` | DB non-null, blank not allowed; validators | Stores the volume usage warning percent required by the CoreSettings contract. |
| `volume_release_retention_days` | `PositiveIntegerField` | no | no | `30` | DB non-null, blank not allowed; validators | Stores the volume release retention days required by the CoreSettings contract. |
| `build_slot_lease_seconds` | `PositiveIntegerField` | no | no | `900` | DB non-null, blank not allowed | Stores the build slot lease seconds required by the CoreSettings contract. |
| `deploy_timeout_minutes` | `PositiveIntegerField` | no | no | `10` | DB non-null, blank not allowed | Deployment relationship used for execution/provenance correlation. |
| `queued_timeout_minutes` | `PositiveIntegerField` | no | no | `10` | DB non-null, blank not allowed | Stores the queued timeout minutes required by the CoreSettings contract. |
| `stop_timeout_minutes` | `PositiveIntegerField` | no | no | `5` | DB non-null, blank not allowed | Stores the stop timeout minutes required by the CoreSettings contract. |
| `unexpected_death_grace_seconds` | `PositiveIntegerField` | no | no | `15` | DB non-null, blank not allowed | Stores the unexpected death grace seconds required by the CoreSettings contract. |
| `monitor_enabled` | `BooleanField` | no | no | `True` | DB non-null, blank not allowed | Stores the monitor enabled required by the CoreSettings contract. |
| `monitor_interval_seconds` | `PositiveIntegerField` | no | no | `30` | DB non-null, blank not allowed | Stores the monitor interval seconds required by the CoreSettings contract. |
| `monitor_batch_size` | `PositiveIntegerField` | no | no | `100` | DB non-null, blank not allowed | Stores the monitor batch size required by the CoreSettings contract. |
| `monitor_recovery_enabled` | `BooleanField` | no | no | `True` | DB non-null, blank not allowed | Stores the monitor recovery enabled required by the CoreSettings contract. |
| `monitor_max_recovery_attempts` | `PositiveSmallIntegerField` | no | no | `3` | DB non-null, blank not allowed | Stores the monitor max recovery attempts required by the CoreSettings contract. |
| `monitor_stale_base_build_minutes` | `PositiveIntegerField` | no | no | `30` | DB non-null, blank not allowed | Stores the monitor stale base build minutes required by the CoreSettings contract. |
| `monitor_stale_worker_seconds` | `PositiveIntegerField` | no | no | `90` | DB non-null, blank not allowed | Stores the monitor stale worker seconds required by the CoreSettings contract. |
| `monitor_scheduler_lock_seconds` | `PositiveIntegerField` | no | no | `20` | DB non-null, blank not allowed | Stores the monitor scheduler lock seconds required by the CoreSettings contract. |
| `build_cache_enabled` | `BooleanField` | no | no | `True` | DB non-null, blank not allowed | Stores the build cache enabled required by the CoreSettings contract. |
| `build_cache_global_limit_mb` | `PositiveIntegerField` | no | no | `20480` | DB non-null, blank not allowed; validators | Stores the build cache global limit mb required by the CoreSettings contract. |
| `build_cache_user_quota_mb` | `PositiveIntegerField` | no | no | `5120` | DB non-null, blank not allowed; validators | User/actor relationship used for ownership, authorization or auditing. |
| `build_cache_service_quota_mb` | `PositiveIntegerField` | no | no | `2048` | DB non-null, blank not allowed; validators | Service relationship used for workload ownership or runtime correlation. |
| `build_cache_retention_days` | `PositiveIntegerField` | no | no | `30` | DB non-null, blank not allowed; validators | Stores the build cache retention days required by the CoreSettings contract. |
| `build_cache_keep_successful_deployments` | `PositiveSmallIntegerField` | no | no | `3` | DB non-null, blank not allowed; validators | Deployment relationship used for execution/provenance correlation. |
| `build_cache_cleanup_target_percent` | `PositiveSmallIntegerField` | no | no | `80` | DB non-null, blank not allowed; validators | Stores the build cache cleanup target percent required by the CoreSettings contract. |
| `build_cache_batch_size` | `PositiveSmallIntegerField` | no | no | `50` | DB non-null, blank not allowed; validators | Stores the build cache batch size required by the CoreSettings contract. |
| `shell_idle_timeout_minutes` | `PositiveSmallIntegerField` | no | no | `10` | DB non-null, blank not allowed | Stores the shell idle timeout minutes required by the CoreSettings contract. |

### Declaration details

- `base_images_enabled`: `BooleanField` — declaration: `default=True, verbose_name=_("Use base runtime image cache"), help_text=_("Reuse registered PHP, Python, Node and other runtime base images during deployment."),`
- `base_images_auto_build`: `BooleanField` — declaration: `default=True, verbose_name=_("Auto-build missing base images"), help_text=_("Build a requested runtime base image automatically when it is not available on the Docker host."),`
- `base_images_retain_after_deploy`: `BooleanField` — declaration: `default=True, verbose_name=_("Keep base images after deployment"), help_text=_("When disabled, an unused base image is removed after the deployment releases its lease. Shared images are kept until no active deployment uses them."),`
- `base_image_build_timeout_minutes`: `PositiveIntegerField` — declaration: `default=10, validators=[MinValueValidator(1), MaxValueValidator(1440)], verbose_name=_("Base image build/wait timeout (minutes)"), help_text=_("Dedicated lifecycle budget for a base-image build or shared wait. This is separate from the application deployment timeout."),`
- `base_images_auto_register_existing`: `BooleanField` — declaration: `default=True, verbose_name=_("Register existing Docker images"), help_text=_("Adopt matching runtime images already present on the Docker host instead of rebuilding them."),`
- `auto_public_url_handling`: `BooleanField` — declaration: `default=True, verbose_name=_("Automatic public/asset URL handling"), help_text=_("When enabled, app deployments receive a secure public URL/asset URL default behind the platform proxy. Disable to let the application manage its own URL scheme/path."),`
- `default_public_url_prefix`: `CharField` — declaration: `default="", max_length=500, blank=True, verbose_name=_("Default public URL prefix"), help_text=_("Optional operator default for public URL generation. Tenant custom values can override only when explicitly requested."),`
- `mirror_docker`: `CharField` — declaration: `default="docker.arvancloud.ir", max_length=255, verbose_name=_("Docker registry mirror")`
- `mirror_python`: `CharField` — declaration: `default="https://mirror-pypi.runflare.com/simple", max_length=500, verbose_name=_("PyPI mirror")`
- `mirror_npm`: `CharField` — declaration: `default="https://package-mirror.liara.ir/repository/npm/", max_length=500, verbose_name=_("npm registry")`
- `mirror_composer`: `CharField` — declaration: `default="https://package-mirror.liara.ir/repository/composer/", max_length=500, verbose_name=_("Composer mirror")`
- `mirror_apt`: `CharField` — declaration: `default="http://repo.iut.ac.ir/debian/", max_length=500, verbose_name=_("APT/Debian mirror")`
- `mirror_go`: `CharField` — declaration: `default="", max_length=500, blank=True, verbose_name=_("Go module proxy")`
- `build_resource_mode`: `CharField` — declaration: `default="static", max_length=16, choices=(("static", "Static"), ("plan", "Plan capped")), verbose_name=_("Build resource mode")`
- `build_pids_limit`: `PositiveIntegerField` — declaration: `default=2048, verbose_name=_("Build PID limit")`
- `build_shm_mb`: `PositiveIntegerField` — declaration: `default=64, verbose_name=_("Build shared memory (MB)")`
- `build_parallelism`: `PositiveSmallIntegerField` — declaration: `default=1, verbose_name=_("Maximum concurrent Docker builds"), help_text=_("Global build concurrency across workers."),`
- `build_wait_minutes`: `PositiveSmallIntegerField` — declaration: `default=5, verbose_name=_("Build slot wait timeout (minutes)"), help_text=_("Maximum time a deployment waits for a Docker build slot."),`
- `build_max_cpu`: `FloatField` — declaration: `default=1.0, verbose_name=_("Build CPU shares weight"), help_text=_("Operator-only relative Docker CPU scheduling weight. This is not a hard CPU quota."),`
- `build_max_ram_mb`: `PositiveIntegerField` — declaration: `default=1024, verbose_name=_("Maximum build RAM (MB)"), help_text=_("Operator-only Docker build memory ceiling."),`
- `volume_usage_warning_percent`: `FloatField` — declaration: `default=90.0, validators=[MinValueValidator(1.0), MaxValueValidator(99.0)], verbose_name=_("Volume usage warning threshold (%)"), help_text=_("Warn users when actual Docker volume usage reaches this percentage of declared logical capacity."),`
- `volume_release_retention_days`: `PositiveIntegerField` — declaration: `default=30, validators=[MinValueValidator(1), MaxValueValidator(3650)], verbose_name=_("Released volume retention (days)"), help_text=_( "How long released volume data remains physically retained after logical " "Service quota is freed. Expired released volumes are reclaimed automatically." ),`
- `build_slot_lease_seconds`: `PositiveIntegerField` — declaration: `default=900, verbose_name=_("Build slot lease (seconds)"), help_text=_("Lease duration used to recover abandoned build slots."),`
- `deploy_timeout_minutes`: `PositiveIntegerField` — declaration: `default=10, verbose_name=_("Deployment timeout (minutes)"), help_text=_("Maximum time for an active deployment pipeline."),`
- `queued_timeout_minutes`: `PositiveIntegerField` — declaration: `default=10, verbose_name=_("Queued/deploying timeout (minutes)"), help_text=_("Maximum time a service may remain queued or deploying."),`
- `stop_timeout_minutes`: `PositiveIntegerField` — declaration: `default=5, verbose_name=_("Stop timeout (minutes)"), help_text=_("Maximum time allowed for an intentional service stop."),`
- `unexpected_death_grace_seconds`: `PositiveIntegerField` — declaration: `default=15, verbose_name=_("Unexpected container death grace (seconds)"),`
- `monitor_enabled`: `BooleanField` — declaration: `default=True, verbose_name=_("Enable deployment monitor"), help_text=_("Run automatic reconciliation and recovery."),`
- `monitor_interval_seconds`: `PositiveIntegerField` — declaration: `default=30, verbose_name=_("Monitor interval (seconds)"), help_text=_("Actual monitor cadence. Celery Beat provides a lightweight pulse."),`
- `monitor_batch_size`: `PositiveIntegerField` — declaration: `default=100, verbose_name=_("Monitor batch size"), help_text=_("Maximum deployments/services inspected per monitor tick."),`
- `monitor_recovery_enabled`: `BooleanField` — declaration: `default=True, verbose_name=_("Enable automatic recovery"),`
- `monitor_max_recovery_attempts`: `PositiveSmallIntegerField` — declaration: `default=3, verbose_name=_("Maximum recovery attempts"),`
- `monitor_stale_base_build_minutes`: `PositiveIntegerField` — declaration: `default=30, verbose_name=_("Legacy base-image timeout setting"), help_text=_( "Deprecated compatibility field. Base-image lifecycle timing is controlled " "by base_image_build_timeout_minutes and this field no longer provides an independent timeout." ),`
- `monitor_stale_worker_seconds`: `PositiveIntegerField` — declaration: `default=90, verbose_name=_("Stale worker heartbeat (seconds)"),`
- `monitor_scheduler_lock_seconds`: `PositiveIntegerField` — declaration: `default=20, verbose_name=_("Monitor scheduler lock (seconds)"),`
- `build_cache_enabled`: `BooleanField` — declaration: `default=True, verbose_name=_("Enable Docker build cache governance"), help_text=_("Enable automatic global BuildKit garbage collection and tenant application-image retention."),`
- `build_cache_global_limit_mb`: `PositiveIntegerField` — declaration: `default=20480, validators=[MinValueValidator(1024), MaxValueValidator(1048576)], verbose_name=_("Global build cache limit (MB)"), help_text=_("Maximum target size for Docker BuildKit cache on each managed Docker daemon."),`
- `build_cache_user_quota_mb`: `PositiveIntegerField` — declaration: `default=5120, validators=[MinValueValidator(128), MaxValueValidator(1048576)], verbose_name=_("Default user cache quota (MB)"), help_text=_("Logical application-image cache quota inherited by users without an override."),`
- `build_cache_service_quota_mb`: `PositiveIntegerField` — declaration: `default=2048, validators=[MinValueValidator(128), MaxValueValidator(1048576)], verbose_name=_("Default service cache quota (MB)"), help_text=_("Logical application-image cache quota inherited by services without an override."),`
- `build_cache_retention_days`: `PositiveIntegerField` — declaration: `default=30, validators=[MinValueValidator(1), MaxValueValidator(3650)], verbose_name=_("Build cache retention (days)"), help_text=_("Age after which non-protected application image artifacts and old BuildKit records become cleanup candidates."),`
- `build_cache_keep_successful_deployments`: `PositiveSmallIntegerField` — declaration: `default=3, validators=[MaxValueValidator(100)], verbose_name=_("Retained successful deployments"), help_text=_("Newest successful deployments per service remain protected from tenant cache GC."),`
- `build_cache_cleanup_target_percent`: `PositiveSmallIntegerField` — declaration: `default=80, validators=[MinValueValidator(50), MaxValueValidator(95)], verbose_name=_("Global cleanup target (%)"), help_text=_("After global cleanup, BuildKit is asked to reduce cache toward this percentage of the global limit."),`
- `build_cache_batch_size`: `PositiveSmallIntegerField` — declaration: `default=50, validators=[MinValueValidator(1), MaxValueValidator(500)], verbose_name=_("Cache GC batch size"), help_text=_("Maximum tenant image groups reclaimed in one maintenance run."),`
- `shell_idle_timeout_minutes`: `PositiveSmallIntegerField` — declaration: `default=10, verbose_name=_("Restricted shell idle timeout (minutes)"), help_text=_("Close inactive shell sessions after this many minutes. Commands and file operations refresh activity."),`

## How to interpret this table

- **DB NULL** describes database nullability; **Blank** describes Django validation/form optionality and is not interchangeable with NULL.
- Defaults may be callables or project helpers, so the displayed expression describes the source contract rather than a single static value.
- Relationship fields also carry deletion semantics through `on_delete`; the relation is therefore part of the lifecycle behavior of the model.
- JSON fields deliberately hold structured state/configuration; their deeper schema is documented by the owning app's contract pages.
- For inherited fields, read the model's base class before assuming a missing `id`, timestamp or permission field is absent.
