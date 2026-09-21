from django.conf import settings
from django.db import migrations, models
from uuid import uuid4
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        ("services", "0018_revision_source_deploy"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.AddField(
            model_name="service",
            name="source_kind",
            field=models.CharField(
                choices=[
                    ("archive", "Archive"),
                    ("git", "Git"),
                    ("dockerfile", "Dockerfile"),
                    ("image", "Existing image"),
                    ("compose", "Compose"),
                    ("catalog", "Catalog"),
                    ("generated", "Generated"),
                ],
                default="archive",
                max_length=20,
            ),
        ),
        migrations.AddField(
            model_name="service",
            name="source_config",
            field=models.JSONField(blank=True, default=dict),
        ),
        migrations.AddField(
            model_name="service",
            name="build_config",
            field=models.JSONField(blank=True, default=dict),
        ),
        migrations.AddField(
            model_name="service",
            name="runtime_config",
            field=models.JSONField(blank=True, default=dict),
        ),
        migrations.AddField(
            model_name="service",
            name="desired_state",
            field=models.CharField(
                choices=[
                    ("stopped", "Stopped"),
                    ("running", "Running"),
                    ("deleted", "Deleted"),
                ],
                default="stopped",
                max_length=16,
            ),
        ),
        migrations.CreateModel(
            name="ServiceSecret",
            fields=[
                ("id", models.UUIDField(default=uuid4, editable=False, primary_key=True, serialize=False)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("key", models.CharField(max_length=128)),
                ("current_version", models.PositiveIntegerField(default=0)),
                ("description", models.CharField(blank=True, default="", max_length=255)),
                ("metadata", models.JSONField(blank=True, default=dict)),
                ("enabled", models.BooleanField(default=True)),
                (
                    "service",
                    models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="secrets", to="services.service"),
                ),
            ],
            options={"ordering": ("key",)},
        ),
        migrations.CreateModel(
            name="ServiceSecretVersion",
            fields=[
                ("id", models.UUIDField(default=uuid4, editable=False, primary_key=True, serialize=False)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("version", models.PositiveIntegerField()),
                ("ciphertext", models.TextField()),
                ("note", models.CharField(blank=True, default="", max_length=255)),
                (
                    "created_by",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="service_secret_versions",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "secret",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="versions",
                        to="services.servicesecret",
                    ),
                ),
            ],
            options={"ordering": ("-version",)},
        ),
        migrations.CreateModel(
            name="ServiceEnvironmentVariable",
            fields=[
                ("id", models.UUIDField(default=uuid4, editable=False, primary_key=True, serialize=False)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("key", models.CharField(max_length=128)),
                ("value", models.TextField(blank=True, default="")),
                ("scope", models.CharField(choices=[("build", "Build"), ("runtime", "Runtime"), ("both", "Build and runtime")], default="runtime", max_length=16)),
                ("enabled", models.BooleanField(default=True)),
                ("metadata", models.JSONField(blank=True, default=dict)),
                (
                    "secret",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="environment_variables",
                        to="services.servicesecret",
                    ),
                ),
                (
                    "service",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="environment_variables",
                        to="services.service",
                    ),
                ),
            ],
            options={"ordering": ("key",)},
        ),
        migrations.CreateModel(
            name="ServiceEndpoint",
            fields=[
                ("id", models.UUIDField(default=uuid4, editable=False, primary_key=True, serialize=False)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("name", models.CharField(max_length=64)),
                ("target_port", models.PositiveIntegerField()),
                ("published_port", models.PositiveIntegerField(blank=True, null=True)),
                ("protocol", models.CharField(choices=[("http", "HTTP"), ("https", "HTTPS"), ("tcp", "TCP"), ("udp", "UDP"), ("ws", "WebSocket")], default="http", max_length=16)),
                ("exposure", models.CharField(choices=[("public", "Public"), ("internal", "Internal")], default="public", max_length=16)),
                ("hostname", models.CharField(blank=True, default="", max_length=255)),
                ("path", models.CharField(blank=True, default="", max_length=255)),
                ("tls", models.BooleanField(default=False)),
                ("enabled", models.BooleanField(default=True)),
                ("metadata", models.JSONField(blank=True, default=dict)),
                (
                    "process",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="endpoints",
                        to="services.serviceprocess",
                    ),
                ),
                (
                    "service",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="endpoints",
                        to="services.service",
                    ),
                ),
            ],
            options={"ordering": ("name",)},
        ),
        migrations.CreateModel(
            name="ServiceNetworkAttachment",
            fields=[
                ("id", models.UUIDField(default=uuid4, editable=False, primary_key=True, serialize=False)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("alias", models.CharField(blank=True, default="", max_length=128)),
                ("internal", models.BooleanField(default=False)),
                ("metadata", models.JSONField(blank=True, default=dict)),
                (
                    "network",
                    models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="service_attachments", to="services.privatenetwork"),
                ),
                (
                    "service",
                    models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="network_attachments", to="services.service"),
                ),
            ],
        ),
        migrations.CreateModel(
            name="DatabaseResource",
            fields=[
                ("id", models.UUIDField(default=uuid4, editable=False, primary_key=True, serialize=False)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("name", models.CharField(max_length=64)),
                ("engine", models.CharField(choices=[("mysql", "MySQL"), ("mariadb", "MariaDB"), ("postgresql", "PostgreSQL"), ("mongodb", "MongoDB"), ("redis", "Redis"), ("oracle", "Oracle")], max_length=32)),
                ("host", models.CharField(blank=True, default="", max_length=255)),
                ("port", models.PositiveIntegerField(blank=True, null=True)),
                ("database_name", models.CharField(blank=True, default="", max_length=128)),
                ("access_policy", models.JSONField(blank=True, default=dict)),
                ("metadata", models.JSONField(blank=True, default=dict)),
                ("status", models.CharField(default="provisioning", max_length=20)),
                (
                    "owner",
                    models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="database_resources", to=settings.AUTH_USER_MODEL),
                ),
                (
                    "provider_service",
                    models.OneToOneField(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="database_resource", to="services.service"),
                ),
            ],
        ),
        migrations.CreateModel(
            name="ServiceDatabaseBinding",
            fields=[
                ("id", models.UUIDField(default=uuid4, editable=False, primary_key=True, serialize=False)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("alias", models.CharField(default="default", max_length=64)),
                ("env_prefix", models.CharField(default="DB", max_length=32)),
                ("access_mode", models.CharField(default="rw", max_length=16)),
                ("metadata", models.JSONField(blank=True, default=dict)),
                (
                    "database",
                    models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="bindings", to="services.databaseresource"),
                ),
                (
                    "service",
                    models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="database_bindings", to="services.service"),
                ),
            ],
        ),
        migrations.AddConstraint(
            model_name="servicesecret",
            constraint=models.UniqueConstraint(fields=("service", "key"), name="uniq_service_secret_key"),
        ),
        migrations.AddConstraint(
            model_name="servicesecretversion",
            constraint=models.UniqueConstraint(fields=("secret", "version"), name="uniq_service_secret_version"),
        ),
        migrations.AddConstraint(
            model_name="serviceenvironmentvariable",
            constraint=models.UniqueConstraint(fields=("service", "key"), name="uniq_service_environment_key"),
        ),
        migrations.AddConstraint(
            model_name="serviceendpoint",
            constraint=models.UniqueConstraint(fields=("service", "name"), name="uniq_service_endpoint_name"),
        ),
        migrations.AddConstraint(
            model_name="servicenetworkattachment",
            constraint=models.UniqueConstraint(fields=("service", "network"), name="uniq_service_network_attachment"),
        ),
        migrations.AddConstraint(
            model_name="databaseresource",
            constraint=models.UniqueConstraint(fields=("owner", "name"), name="uniq_database_resource_owner_name"),
        ),
        migrations.AddConstraint(
            model_name="servicedatabasebinding",
            constraint=models.UniqueConstraint(fields=("service", "database", "alias"), name="uniq_service_database_binding"),
        ),
    ]
