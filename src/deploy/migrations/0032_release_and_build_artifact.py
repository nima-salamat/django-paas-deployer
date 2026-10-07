from django.db import migrations, models
import django.db.models.deletion
import django.utils.timezone
import uuid


class Migration(migrations.Migration):
    dependencies = [
        ("deploy", "0031_canonical_deploy_state"),
        ("services", "0031_service_process_replicas"),
    ]

    operations = [
        migrations.CreateModel(
            name="BuildArtifact",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False, verbose_name="ID")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("digest", models.CharField(db_index=True, max_length=255, unique=True)),
                ("image_ref", models.CharField(max_length=384)),
                ("source_digest", models.CharField(blank=True, default="", max_length=64)),
                ("build_definition_digest", models.CharField(blank=True, default="", max_length=64)),
                ("base_image_digests", models.JSONField(blank=True, default=list)),
                ("build_context_identity", models.CharField(blank=True, default="", max_length=255)),
                ("builder_backend", models.CharField(blank=True, default="", max_length=64)),
                ("platform_architecture", models.CharField(blank=True, default="", max_length=64)),
                ("provenance", models.JSONField(blank=True, default=dict)),
                ("created_by", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="build_artifacts", to="users.user")),
            ],
            options={
                "verbose_name": "Build Artifact",
                "verbose_name_plural": "Build Artifacts",
            },
        ),
        migrations.CreateModel(
            name="Release",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False, verbose_name="ID")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("identity_fingerprint", models.CharField(db_index=True, max_length=64, unique=True)),
                ("runtime_spec", models.JSONField(blank=True, default=dict)),
                ("rollout_policy", models.JSONField(blank=True, default=dict)),
                ("health_policy", models.JSONField(blank=True, default=dict)),
                ("release_command", models.JSONField(blank=True, default=dict)),
                ("status", models.CharField(choices=[("prepared", "Prepared"), ("ready", "Ready"), ("promoted", "Promoted"), ("retired", "Retired"), ("failed", "Failed"), ("rolled_back", "Rolled back")], db_index=True, default="prepared", max_length=24)),
                ("provenance", models.JSONField(blank=True, default=dict)),
                ("promoted_at", models.DateTimeField(blank=True, null=True)),
                ("retired_at", models.DateTimeField(blank=True, null=True)),
                ("artifact", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name="releases", to="deploy.buildartifact")),
                ("created_by", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="releases", to="users.user")),
                ("previous_release", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="successor_releases", to="deploy.release")),
                ("revision", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="releases", to="services.servicerevision")),
                ("service", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="releases", to="services.service")),
            ],
            options={
                "verbose_name": "Release",
                "verbose_name_plural": "Releases",
            },
        ),
        migrations.AddField(
            model_name="deploy",
            name="release",
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="deployment_attempts", to="deploy.release"),
        ),
        migrations.AddField(
            model_name="deploy",
            name="artifact",
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="deployment_attempts", to="deploy.buildartifact"),
        ),
        migrations.AddConstraint(
            model_name="release",
            constraint=models.UniqueConstraint(fields=("service", "revision", "identity_fingerprint"), name="uniq_release_identity_per_revision"),
        ),
    ]
