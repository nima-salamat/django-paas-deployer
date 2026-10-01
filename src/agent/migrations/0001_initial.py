import uuid

from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion

from agent.scopes import default_agent_scopes


class Migration(migrations.Migration):
    initial = True
    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="Agent",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("name", models.CharField(max_length=100)),
                ("description", models.TextField(blank=True, default="")),
                ("status", models.CharField(choices=[("active","Active"),("disabled","Disabled"),("revoked","Revoked")], db_index=True, default="active", max_length=16)),
                ("scopes", models.JSONField(blank=True, default=default_agent_scopes)),
                ("metadata", models.JSONField(blank=True, default=dict)),
                ("last_used_at", models.DateTimeField(blank=True, db_index=True, null=True)),
                ("disabled_at", models.DateTimeField(blank=True, null=True)),
                ("revoked_at", models.DateTimeField(blank=True, null=True)),
                ("user", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="agents", to=settings.AUTH_USER_MODEL)),
            ],
            options={
                "ordering": ("user_id", "name", "created_at"),
                "indexes": [
                    models.Index(fields=["user", "status"], name="agent_user_status_idx"),
                    models.Index(fields=["status", "-last_used_at"], name="agent_status_last_idx"),
                ],
                "constraints": [models.UniqueConstraint(fields=("user", "name"), name="uniq_agent_user_name")],
            },
        ),
        migrations.CreateModel(
            name="AgentCredential",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("token_prefix", models.CharField(db_index=True, max_length=32)),
                ("token_hash", models.CharField(editable=False, max_length=64, unique=True)),
                ("token_type", models.CharField(choices=[("access","Access token")], default="access", max_length=16)),
                ("expires_at", models.DateTimeField(blank=True, db_index=True, null=True)),
                ("revoked_at", models.DateTimeField(blank=True, db_index=True, null=True)),
                ("last_used_at", models.DateTimeField(blank=True, db_index=True, null=True)),
                ("last_used_ip", models.GenericIPAddressField(blank=True, null=True)),
                ("metadata", models.JSONField(blank=True, default=dict)),
                ("agent", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="credentials", to="agent.agent")),
            ],
            options={
                "ordering": ("-created_at",),
                "indexes": [
                    models.Index(fields=["agent", "revoked_at", "expires_at"], name="agent_credential_state_idx"),
                    models.Index(fields=["token_prefix", "revoked_at"], name="agent_token_prefix_idx"),
                ],
            },
        ),
        migrations.CreateModel(
            name="AgentEnrollmentToken",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("token_prefix", models.CharField(db_index=True, max_length=32)),
                ("token_hash", models.CharField(db_index=False, max_length=64, unique=True, editable=False)),
                ("expires_at", models.DateTimeField(db_index=True)),
                ("used_at", models.DateTimeField(blank=True, db_index=True, null=True)),
                ("issued_from_ip", models.GenericIPAddressField(blank=True, null=True)),
                ("agent", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="enrollments", to="agent.agent")),
            ],
            options={
                "ordering": ("-created_at",),
                "indexes": [models.Index(fields=["agent", "used_at", "expires_at"], name="agent_enrollment_state_idx")],
            },
        ),
        migrations.CreateModel(
            name="AgentAuditEvent",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("action", models.CharField(db_index=True, max_length=96)),
                ("resource_type", models.CharField(blank=True, default="", max_length=64)),
                ("resource_id", models.CharField(blank=True, default="", max_length=255)),
                ("request_id", models.CharField(db_index=True, max_length=64)),
                ("occurred_at", models.DateTimeField(auto_now_add=True, db_index=True)),
                ("success", models.BooleanField(db_index=True, default=False)),
                ("http_status", models.PositiveSmallIntegerField(blank=True, null=True)),
                ("error_code", models.CharField(blank=True, default="", max_length=96)),
                ("failure_domain", models.CharField(blank=True, default="", max_length=32)),
                ("retryability", models.CharField(blank=True, default="", max_length=16)),
                ("visibility", models.CharField(blank=True, default="client", max_length=16)),
                ("resource_effect", models.CharField(blank=True, default="unchanged", max_length=32)),
                ("certainty", models.CharField(blank=True, default="known", max_length=16)),
                ("duration_ms", models.PositiveIntegerField(blank=True, null=True)),
                ("metadata", models.JSONField(blank=True, default=dict)),
                ("agent", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="audit_events", to="agent.agent")),
                ("credential", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="audit_events", to="agent.agentcredential")),
                ("user", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="agent_audit_events", to=settings.AUTH_USER_MODEL)),
            ],
            options={
                "ordering": ("-occurred_at", "-id"),
                "indexes": [
                    models.Index(fields=["agent", "-occurred_at"], name="agent_audit_agent_time_idx"),
                    models.Index(fields=["user", "-occurred_at"], name="agent_audit_user_time_idx"),
                    models.Index(fields=["resource_type", "resource_id", "-occurred_at"], name="agent_audit_resource_time_idx"),
                ],
            },
        ),
        migrations.CreateModel(
            name="AgentIdempotencyRecord",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("key", models.CharField(max_length=255)),
                ("method", models.CharField(max_length=16)),
                ("path", models.CharField(max_length=512)),
                ("request_hash", models.CharField(max_length=64)),
                ("state", models.CharField(choices=[("processing","Processing"),("complete","Complete")], default="processing", max_length=16)),
                ("status_code", models.PositiveSmallIntegerField(blank=True, null=True)),
                ("response_body", models.JSONField(blank=True, null=True)),
                ("expires_at", models.DateTimeField(db_index=True)),
                ("agent", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="idempotency_records", to="agent.agent")),
            ],
            options={
                "constraints": [models.UniqueConstraint(fields=("agent","key"), name="uniq_agent_idempotency_key")],
                "indexes": [models.Index(fields=["agent","expires_at"], name="agent_idem_agent_exp_idx")],
            },
        ),
    ]
