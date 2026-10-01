from django.db import migrations, models
import django.db.models.deletion
import django.utils.timezone
import uuid


class Migration(migrations.Migration):
    dependencies = [
        ("deploy", "0025_alter_buildcacheartifact_created_at_and_more"),
    ]

    operations = [
        migrations.AddField(model_name="deploy", name="cleanup_failures", field=models.JSONField(blank=True, default=list)),
        migrations.AddField(model_name="deploy", name="cleanup_status", field=models.CharField(choices=[("not_required", "Not required"), ("pending", "Pending"), ("clean", "Clean"), ("degraded", "Degraded"), ("critical", "Critical")], default="not_required", max_length=24)),
        migrations.AddField(model_name="deploy", name="image_digest", field=models.CharField(blank=True, default="", max_length=255)),
        migrations.AddField(model_name="deploy", name="image_ref", field=models.CharField(blank=True, default="", max_length=384)),
        migrations.AddField(model_name="deploy", name="reconciliation_required", field=models.BooleanField(db_index=True, default=False)),
        migrations.AddField(model_name="deploy", name="release_id", field=models.UUIDField(default=uuid.uuid4, db_index=True, editable=False, unique=True)),
        migrations.AddField(model_name="deploy", name="runtime_revision_id", field=models.CharField(blank=True, db_index=True, default="", max_length=255)),
        migrations.AddField(model_name="deploy", name="runtime_spec", field=models.JSONField(blank=True, null=True)),
        migrations.AddField(model_name="deploy", name="runtime_spec_sha256", field=models.CharField(blank=True, default="", max_length=64)),
        migrations.AddField(model_name="deploy", name="source_revision", field=models.CharField(blank=True, db_index=True, default="", max_length=255)),
        migrations.CreateModel(
            name="DeploymentResource",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("kind", models.CharField(max_length=64)),
                ("name", models.CharField(max_length=255)),
                ("runtime_id", models.CharField(blank=True, default="", max_length=255)),
                ("state", models.CharField(choices=[("planned","Planned"),("created","Created"),("started","Started"),("ready","Ready"),("active","Active"),("retired","Retired"),("failed","Failed"),("cleanup_pending","Cleanup pending")], default="planned", max_length=32)),
                ("owned", models.BooleanField(default=True)),
                ("metadata", models.JSONField(blank=True, default=dict)),
                ("last_error", models.TextField(blank=True, default="")),
                ("retired_at", models.DateTimeField(blank=True, null=True)),
                ("deployment", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="resources", to="deploy.deploy")),
            ],
        ),
        migrations.CreateModel(
            name="DeploymentEventOutbox",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("event_id", models.UUIDField(db_index=True, default=uuid.uuid4, editable=False, unique=True)),
                ("service_id", models.CharField(blank=True, db_index=True, default="", max_length=255)),
                ("event_type", models.CharField(max_length=128)),
                ("stage", models.CharField(max_length=64)),
                ("level", models.CharField(default="info", max_length=16)),
                ("occurred_at", models.DateTimeField(db_index=True, default=django.utils.timezone.now)),
                ("payload", models.JSONField(default=dict)),
                ("dispatched_at", models.DateTimeField(blank=True, db_index=True, null=True)),
                ("attempts", models.PositiveIntegerField(default=0)),
                ("last_error", models.TextField(blank=True, default="")),
                ("deployment", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="event_outbox", to="deploy.deploy")),
            ],
            options={"ordering": ("occurred_at", "id")},
        ),
        migrations.AddConstraint(model_name="deploymentresource", constraint=models.UniqueConstraint(fields=("deployment", "kind", "name"), name="uniq_deployment_resource")),
        migrations.AddIndex(model_name="deploymentresource", index=models.Index(fields=("deployment", "state"), name="deploy_resource_deployment_state_idx")),
        migrations.AddIndex(model_name="deploymentresource", index=models.Index(fields=("kind", "name"), name="deploy_resource_kind_name_idx")),
        migrations.AddIndex(model_name="deploymenteventoutbox", index=models.Index(fields=("dispatched_at", "occurred_at"), name="deploy_event_dispatched_idx")),
        migrations.AddIndex(model_name="deploymenteventoutbox", index=models.Index(fields=("deployment", "occurred_at"), name="deploy_event_deployment_idx")),
    ]
