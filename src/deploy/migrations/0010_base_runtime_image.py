from django.db import migrations, models
import uuid


class Migration(migrations.Migration):
    dependencies = [("deploy", "0009_deploy_created_by")]

    operations = [
        migrations.CreateModel(
            name="BaseRuntimeImage",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False, verbose_name="ID")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("logical_runtime", models.CharField(max_length=32)),
                ("runtime_version", models.CharField(max_length=32)),
                ("variant", models.CharField(default="default", max_length=32)),
                ("architecture", models.CharField(blank=True, default="", max_length=32)),
                ("docker_host", models.CharField(blank=True, default="", max_length=255)),
                ("source_image", models.CharField(max_length=255)),
                ("image_repository", models.CharField(max_length=255)),
                ("image_tag", models.CharField(max_length=128)),
                ("image_ref", models.CharField(max_length=384)),
                ("image_id", models.CharField(blank=True, default="", max_length=255)),
                ("image_digest", models.CharField(blank=True, default="", max_length=255)),
                ("status", models.CharField(choices=[("pending", "Pending"), ("building", "Building"), ("ready", "Ready"), ("failed", "Failed"), ("disabled", "Disabled")], default="pending", max_length=16)),
                ("enabled", models.BooleanField(default=True)),
                ("auto_build", models.BooleanField(default=True)),
                ("rebuild_requested", models.BooleanField(default=False)),
                ("rebuild_requested_at", models.DateTimeField(blank=True, null=True)),
                ("build_started_at", models.DateTimeField(blank=True, null=True)),
                ("build_completed_at", models.DateTimeField(blank=True, null=True)),
                ("build_count", models.PositiveIntegerField(default=0)),
                ("last_error", models.TextField(blank=True, default="")),
            ],
            options={"ordering": ("logical_runtime", "runtime_version", "variant"), "verbose_name": "Base runtime image", "verbose_name_plural": "Base runtime images"},
        ),
        migrations.AddConstraint(
            model_name="baseruntimeimage",
            constraint=models.UniqueConstraint(fields=("logical_runtime", "runtime_version", "variant", "architecture", "docker_host"), name="uniq_base_runtime_image_host"),
        ),
    ]
