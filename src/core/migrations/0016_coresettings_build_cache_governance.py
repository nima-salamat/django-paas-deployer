from django.db import migrations, models
from django.core.validators import MinValueValidator, MaxValueValidator


class Migration(migrations.Migration):
    dependencies = [
        ("core", "0015_deprecate_legacy_base_timeout_setting"),
    ]

    operations = [
        migrations.AddField(
            model_name="coresettings",
            name="build_cache_enabled",
            field=models.BooleanField(
                default=True,
                help_text="Enable automatic global BuildKit garbage collection and tenant application-image retention.",
                verbose_name="Enable Docker build cache governance",
            ),
        ),
        migrations.AddField(
            model_name="coresettings",
            name="build_cache_global_limit_mb",
            field=models.PositiveIntegerField(
                default=20480,
                validators=[MinValueValidator(1024), MaxValueValidator(1048576)],
                help_text="Maximum target size for Docker BuildKit cache on each managed Docker daemon.",
                verbose_name="Global build cache limit (MB)",
            ),
        ),
        migrations.AddField(
            model_name="coresettings",
            name="build_cache_user_quota_mb",
            field=models.PositiveIntegerField(
                default=5120,
                validators=[MinValueValidator(128), MaxValueValidator(1048576)],
                help_text="Logical application-image cache quota inherited by users without an override.",
                verbose_name="Default user cache quota (MB)",
            ),
        ),
        migrations.AddField(
            model_name="coresettings",
            name="build_cache_service_quota_mb",
            field=models.PositiveIntegerField(
                default=2048,
                validators=[MinValueValidator(128), MaxValueValidator(1048576)],
                help_text="Logical application-image cache quota inherited by services without an override.",
                verbose_name="Default service cache quota (MB)",
            ),
        ),
        migrations.AddField(
            model_name="coresettings",
            name="build_cache_retention_days",
            field=models.PositiveIntegerField(
                default=30,
                validators=[MinValueValidator(1), MaxValueValidator(3650)],
                help_text="Age after which non-protected application image artifacts and old BuildKit records become cleanup candidates.",
                verbose_name="Build cache retention (days)",
            ),
        ),
        migrations.AddField(
            model_name="coresettings",
            name="build_cache_keep_successful_deployments",
            field=models.PositiveSmallIntegerField(
                default=3,
                validators=[MaxValueValidator(100)],
                help_text="Newest successful deployments per service remain protected from tenant cache GC.",
                verbose_name="Retained successful deployments",
            ),
        ),
        migrations.AddField(
            model_name="coresettings",
            name="build_cache_cleanup_target_percent",
            field=models.PositiveSmallIntegerField(
                default=80,
                validators=[MinValueValidator(50), MaxValueValidator(95)],
                help_text="After global cleanup, BuildKit is asked to reduce cache toward this percentage of the global limit.",
                verbose_name="Global cleanup target (%)",
            ),
        ),
        migrations.AddField(
            model_name="coresettings",
            name="build_cache_batch_size",
            field=models.PositiveSmallIntegerField(
                default=50,
                validators=[MinValueValidator(1), MaxValueValidator(500)],
                help_text="Maximum tenant image groups reclaimed in one maintenance run.",
                verbose_name="Cache GC batch size",
            ),
        ),
    ]
