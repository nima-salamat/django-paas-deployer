from django.db import migrations, models
from uuid import uuid4
import django.db.models.deletion
from django.conf import settings


class Migration(migrations.Migration):
    dependencies = [
        ("services", "0016_shell_audit_and_concurrent"),
        ("deploy", "0015_deploy_recovery_operation"),
    ]

    operations = [
        migrations.CreateModel(
            name="ServiceProcess",
            fields=[
                ("id", models.UUIDField(default=uuid4, editable=False, primary_key=True, serialize=False)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("name", models.CharField(max_length=64)),
                ("process_type", models.CharField(default="custom", max_length=32)),
                ("command", models.TextField(blank=True, null=True)),
                ("entrypoint", models.TextField(blank=True, null=True)),
                ("replicas", models.PositiveIntegerField(default=1)),
                ("enabled", models.BooleanField(default=True)),
                ("environment", models.JSONField(blank=True, default=dict)),
                ("healthcheck", models.JSONField(blank=True, default=dict)),
                ("resources", models.JSONField(blank=True, default=dict)),
                ("metadata", models.JSONField(blank=True, default=dict)),
                (
                    "service",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="processes",
                        to="services.service",
                    ),
                ),
            ],
            options={
                "ordering": ("created_at", "name"),
                "constraints": [
                    models.UniqueConstraint(
                        fields=("service", "name"),
                        name="uniq_service_process_name",
                    )
                ],
            },
        ),
        migrations.CreateModel(
            name="ServiceRevision",
            fields=[
                ("id", models.UUIDField(default=uuid4, editable=False, primary_key=True, serialize=False)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "revision_number",
                    models.PositiveIntegerField(),
                ),
                (
                    "state",
                    models.CharField(
                        choices=[
                            ("created", "Created"),
                            ("active", "Active"),
                            ("superseded", "Superseded"),
                            ("failed", "Failed"),
                        ],
                        default="created",
                        max_length=20,
                    ),
                ),
                ("config_snapshot", models.JSONField(default=dict)),
                ("process_snapshot", models.JSONField(default=list)),
                ("secret_keys", models.JSONField(default=list)),
                ("activated_at", models.DateTimeField(blank=True, null=True)),
                (
                    "created_by",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="service_revisions",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "service",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="revisions",
                        to="services.service",
                    ),
                ),
                (
                    "source_deploy",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="source_revisions",
                        to="deploy.deploy",
                    ),
                ),
            ],
            options={
                "ordering": ("-revision_number",),
                "constraints": [
                    models.UniqueConstraint(
                        fields=("service", "revision_number"),
                        name="uniq_service_revision_number",
                    )
                ],
            },
        ),
        migrations.AddField(
            model_name="service",
            name="active_revision",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="active_for_services",
                to="services.servicerevision",
            ),
        ),
    ]
