from django.db import migrations, models
import django.db.models.deletion
import uuid


class Migration(migrations.Migration):
    initial = True
    dependencies = [
        ("users", "0005_alter_user_is_superuser"),
        ("services", "0016_shell_audit_and_concurrent"),
        ("deploy", "0014_deploy_execution_ownership"),
    ]

    operations = [
        migrations.CreateModel(
            name="ApplicationInstance",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("name", models.CharField(max_length=50)),
                ("slug", models.SlugField(max_length=50)),
                ("catalog_id", models.CharField(max_length=64)),
                ("definition_version", models.CharField(max_length=32)),
                ("variant_id", models.CharField(max_length=64)),
                ("config", models.JSONField(blank=True, default=dict)),
                ("secret_config", models.JSONField(blank=True, default=dict)),
                ("status", models.CharField(choices=[("pending", "Pending"), ("deploying", "Deploying"), ("running", "Running"), ("failed", "Failed"), ("cancelled", "Cancelled")], default="pending", max_length=16)),
                ("error_code", models.CharField(blank=True, default="", max_length=96)),
                ("error_message", models.TextField(blank=True, default="")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("deployed_at", models.DateTimeField(blank=True, null=True)),
                ("user", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="application_instances", to="users.user")),
            ],
            options={"ordering": ("-created_at",)},
        ),
        migrations.CreateModel(
            name="ApplicationInstanceService",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("service_key", models.CharField(max_length=64)),
                ("sequence", models.PositiveIntegerField(default=0)),
                ("deploy", models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, related_name="application_binding", to="deploy.deploy")),
                ("instance", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="services", to="app_catalog.applicationinstance")),
                ("service", models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, related_name="application_binding", to="services.service")),
            ],
            options={"ordering": ("sequence", "service_key")},
        ),
        migrations.AddConstraint(
            model_name="applicationinstance",
            constraint=models.UniqueConstraint(fields=("user", "slug"), name="uniq_application_instance_user_slug"),
        ),
        migrations.AddConstraint(
            model_name="applicationinstanceservice",
            constraint=models.UniqueConstraint(fields=("instance", "service_key"), name="uniq_application_instance_service_key"),
        ),
    ]
