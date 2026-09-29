from django.db import migrations, models
from django.core.validators import MinValueValidator, MaxValueValidator
from django.db.models import Q
import django.db.models.deletion
import django.utils.timezone
import uuid


class Migration(migrations.Migration):
    dependencies = [
        ("deploy", "0023_canonical_php_base_runtime_identity"),
        ("services", "0018_revision_source_deploy"),
        ("users", "0003_user_balance_user_national_id_alter_profile_image_and_more"),
    ]

    operations = [
        migrations.CreateModel(
            name="BuildCacheArtifact",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False, verbose_name="ID")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("image_ref", models.CharField(max_length=384)),
                ("image_id", models.CharField(db_index=True, max_length=255)),
                ("image_digest", models.CharField(blank=True, default="", max_length=255)),
                ("size_bytes", models.BigIntegerField(default=0)),
                ("last_used_at", models.DateTimeField(db_index=True, default=django.utils.timezone.now)),
                ("pinned", models.BooleanField(default=False)),
                ("reclaimed_at", models.DateTimeField(blank=True, db_index=True, null=True)),
                ("reclaim_error", models.TextField(blank=True, default="")),
                ("deployment", models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, related_name="cache_artifact", to="deploy.deploy")),
                ("service", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="build_cache_artifacts", to="services.service")),
                ("user", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="build_cache_artifacts", to="users.user")),
            ],
            options={
                "ordering": ("-last_used_at", "-created_at"),
                "verbose_name": "Build cache artifact",
                "verbose_name_plural": "Build cache artifacts",
            },
        ),
        migrations.CreateModel(
            name="BuildCacheQuota",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False, verbose_name="ID")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("quota_mb", models.PositiveIntegerField(blank=True, help_text="Logical application-image cache quota. Null inherits the applicable default.", null=True, validators=[MinValueValidator(128), MaxValueValidator(1048576)], verbose_name="Cache quota (MB)")),
                ("retention_days", models.PositiveIntegerField(blank=True, help_text="How long non-protected application image artifacts may be retained. Null inherits the applicable default.", null=True, validators=[MinValueValidator(1), MaxValueValidator(3650)], verbose_name="Retention (days)")),
                ("keep_successful_deployments", models.PositiveSmallIntegerField(blank=True, help_text="Number of newest successful application deployments to keep protected. Null inherits the applicable default.", null=True, validators=[MaxValueValidator(100)], verbose_name="Keep successful deployments")),
                ("service", models.OneToOneField(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name="build_cache_quota", to="services.service")),
                ("user", models.OneToOneField(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name="build_cache_quota", to="users.user")),
            ],
            options={
                "verbose_name": "Build cache quota",
                "verbose_name_plural": "Build cache quotas",
            },
        ),
        migrations.AddConstraint(
            model_name="buildcachequota",
            constraint=models.CheckConstraint(
                condition=Q(user__isnull=False, service__isnull=True) | Q(user__isnull=True, service__isnull=False),
                name="build_cache_quota_exactly_one_owner",
            ),
        ),
        migrations.AddIndex(model_name="buildcacheartifact", index=models.Index(fields=("service", "reclaimed_at", "last_used_at"), name="deploy_bca_service_gc")),
        migrations.AddIndex(model_name="buildcacheartifact", index=models.Index(fields=("user", "reclaimed_at", "last_used_at"), name="deploy_bca_user_gc")),
        migrations.AddIndex(model_name="buildcacheartifact", index=models.Index(fields=("image_id", "reclaimed_at"), name="deploy_bca_image_gc")),
    ]
