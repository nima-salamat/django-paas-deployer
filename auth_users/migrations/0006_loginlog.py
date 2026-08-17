# Generated manually for LoginLog

from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("auth_users", "0005_loginsettings_allow_login_and_more"),
    ]

    operations = [
        migrations.CreateModel(
            name="LoginLog",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("username", models.CharField(blank=True, db_index=True, default="", max_length=150)),
                ("identifier", models.CharField(blank=True, default="", help_text="Email / phone / username used at login time", max_length=255)),
                ("event", models.CharField(choices=[("success", "Login success"), ("failed", "Login failed"), ("logout", "Logout"), ("password_reset", "Password reset login")], db_index=True, default="success", max_length=20)),
                ("method", models.CharField(choices=[("otp", "OTP only"), ("password", "Password only"), ("otp_password", "OTP + Password"), ("token", "Token / session"), ("other", "Other")], default="other", max_length=20)),
                ("success", models.BooleanField(db_index=True, default=True)),
                ("ip_address", models.GenericIPAddressField(blank=True, db_index=True, null=True)),
                ("user_agent", models.CharField(blank=True, default="", max_length=500)),
                ("failure_reason", models.CharField(blank=True, default="", max_length=255)),
                ("extra", models.JSONField(blank=True, default=dict)),
                ("created_at", models.DateTimeField(auto_now_add=True, db_index=True)),
                ("user", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="login_logs", to=settings.AUTH_USER_MODEL)),
            ],
            options={
                "verbose_name": "Login Log",
                "verbose_name_plural": "Login Logs",
                "ordering": ["-created_at"],
            },
        ),
        migrations.AddIndex(
            model_name="loginlog",
            index=models.Index(fields=["-created_at", "event"], name="auth_users__created_f0a1b2_idx"),
        ),
        migrations.AddIndex(
            model_name="loginlog",
            index=models.Index(fields=["user", "-created_at"], name="auth_users__user_id_c3d4e5_idx"),
        ),
    ]
