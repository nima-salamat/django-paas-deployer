from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion
import uuid


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("auth_users", "0007_rename_auth_users__created_f0a1b2_idx_auth_users__created_4ae7e4_idx_and_more"),
    ]

    operations = [
        migrations.AddField(
            model_name="loginsettings",
            name="max_active_sessions",
            field=models.PositiveSmallIntegerField(
                default=5,
                help_text="Maximum number of active authenticated sessions per user.",
            ),
        ),
        migrations.AddField(
            model_name="loginsettings",
            name="session_eviction_policy",
            field=models.CharField(
                choices=[
                    ("revoke_oldest", "Revoke oldest session"),
                    ("reject_new", "Reject new login"),
                ],
                default="revoke_oldest",
                help_text="How a login behaves when the active-session limit is reached.",
                max_length=24,
            ),
        ),
        migrations.CreateModel(
            name="Device",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("public_id", models.UUIDField(db_index=True, default=uuid.uuid4, editable=False, unique=True)),
                ("name", models.CharField(blank=True, default="", max_length=120)),
                ("platform", models.CharField(blank=True, default="", max_length=64)),
                ("client", models.CharField(blank=True, default="", max_length=120)),
                ("user_agent", models.CharField(blank=True, default="", max_length=500)),
                ("last_ip", models.GenericIPAddressField(blank=True, null=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("last_seen_at", models.DateTimeField(auto_now=True)),
                ("revoked_at", models.DateTimeField(blank=True, db_index=True, null=True)),
                ("user", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="auth_devices", to=settings.AUTH_USER_MODEL)),
            ],
            options={
                "ordering": ["-last_seen_at"],
                "indexes": [
                    models.Index(fields=["user", "revoked_at"], name="auth_users__user_id_9c7cb7_idx"),
                    models.Index(fields=["user", "-last_seen_at"], name="auth_users__user_id_e0ebe1_idx"),
                ],
            },
        ),
        migrations.CreateModel(
            name="UserSession",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("session_id", models.CharField(db_index=True, editable=False, max_length=128, unique=True)),
                ("credential_hash", models.CharField(editable=False, max_length=128)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("last_seen_at", models.DateTimeField(auto_now=True)),
                ("expires_at", models.DateTimeField(db_index=True)),
                ("revoked_at", models.DateTimeField(blank=True, db_index=True, null=True)),
                ("auth_generation", models.PositiveIntegerField(default=1)),
                ("last_ip", models.GenericIPAddressField(blank=True, null=True)),
                ("user_agent", models.CharField(blank=True, default="", max_length=500)),
                ("metadata", models.JSONField(blank=True, default=dict)),
                ("device", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="sessions", to="auth_users.device")),
                ("user", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="auth_sessions", to=settings.AUTH_USER_MODEL)),
            ],
            options={
                "ordering": ["-created_at"],
                "indexes": [
                    models.Index(fields=["user", "revoked_at", "expires_at"], name="auth_users__user_id_ecd16b_idx"),
                    models.Index(fields=["device", "revoked_at"], name="auth_users__device__24f366_idx"),
                ],
            },
        ),
    ]
