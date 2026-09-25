import uuid

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("services", "0015_shell_session"),
    ]

    operations = [
        migrations.RemoveConstraint(
            model_name="shellsession",
            name="uniq_active_shell_session_service",
        ),
        migrations.CreateModel(
            name="ShellAuditEvent",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("action", models.CharField(db_index=True, max_length=32)),
                ("command", models.TextField(blank=True, default="")),
                ("path", models.CharField(blank=True, default="", max_length=1024)),
                ("cwd", models.CharField(blank=True, default="", max_length=512)),
                ("exit_code", models.IntegerField(blank=True, null=True)),
                ("success", models.BooleanField(default=True)),
                ("detail", models.TextField(blank=True, default="")),
                ("meta", models.JSONField(blank=True, default=dict)),
                ("output_preview", models.TextField(blank=True, default="")),
                (
                    "service",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="shell_audit_events",
                        to="services.service",
                    ),
                ),
                (
                    "session",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="audit_events",
                        to="services.shellsession",
                    ),
                ),
                (
                    "user",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="shell_audit_events",
                        to="users.user",
                    ),
                ),
            ],
            options={
                "ordering": ("-created_at",),
            },
        ),
        migrations.AddIndex(
            model_name="shellauditevent",
            index=models.Index(fields=["service", "-created_at"], name="svc_shell_audit_svc_created"),
        ),
        migrations.AddIndex(
            model_name="shellauditevent",
            index=models.Index(fields=["service", "action", "-created_at"], name="svc_shell_audit_svc_action"),
        ),
        migrations.AddIndex(
            model_name="shellauditevent",
            index=models.Index(fields=["user", "-created_at"], name="svc_shell_audit_user_created"),
        ),
    ]
