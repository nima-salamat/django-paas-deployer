import django.db.models.deletion
import django.utils.timezone
from django.db import migrations, models
import uuid

class Migration(migrations.Migration):
    dependencies = [("services", "0014_servicesharemember")]
    operations = [
        migrations.CreateModel(
            name="ShellSession",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False, verbose_name="ID")),
                ("created_at", models.DateTimeField(auto_now_add=True, verbose_name="Created At")),
                ("updated_at", models.DateTimeField(auto_now=True, verbose_name="Updated At")),
                ("token_hash", models.CharField(max_length=64, unique=True)),
                ("platform", models.CharField(max_length=32)),
                ("root_path", models.CharField(default="/app", max_length=512)),
                ("workdir", models.CharField(default="/app", max_length=512)),
                ("status", models.CharField(choices=[("active", "Active"), ("closed", "Closed"), ("expired", "Expired")], default="active", max_length=16)),
                ("last_used_at", models.DateTimeField(default=django.utils.timezone.now)),
                ("expires_at", models.DateTimeField()),
                ("closed_at", models.DateTimeField(blank=True, null=True)),
                ("service", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="shell_sessions", to="services.service")),
                ("user", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="shell_sessions", to="users.user")),
            ],
            options={"indexes":[models.Index(fields=["service","status","expires_at"], name="services_sh_service_0c4f1e_idx")]},
        ),
        migrations.AddConstraint(
            model_name="shellsession",
            constraint=models.UniqueConstraint(condition=models.Q(status="active"), fields=("service",), name="uniq_active_shell_session_service"),
        ),
    ]
