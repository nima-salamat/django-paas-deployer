from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion
import uuid


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("auth_users", "0008_session_policy_device_usersession"),
    ]

    operations = [
        migrations.AlterField(
            model_name="authcode",
            name="purpose",
            field=models.CharField(
                choices=[
                    ("login", "Login / Verify"),
                    ("signup", "Signup"),
                    ("recovery", "Username Recovery"),
                    ("password_reset", "Password Reset"),
                    ("contact_change", "Contact Change"),
                ],
                default="login",
                max_length=20,
            ),
        ),
        migrations.CreateModel(
            name="UserContactChange",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("public_id", models.UUIDField(db_index=True, default=uuid.uuid4, editable=False, unique=True)),
                ("field", models.CharField(choices=[("email", "Email"), ("phone_number", "Phone number")], db_index=True, max_length=20)),
                ("old_value", models.CharField(blank=True, default="", max_length=255)),
                ("new_value", models.CharField(max_length=255)),
                ("status", models.CharField(choices=[("pending", "Pending"), ("verified", "Verified"), ("cancelled", "Cancelled"), ("expired", "Expired")], db_index=True, default="pending", max_length=12)),
                ("requested_at", models.DateTimeField(auto_now_add=True)),
                ("verified_at", models.DateTimeField(blank=True, null=True)),
                ("cancelled_at", models.DateTimeField(blank=True, null=True)),
                ("requested_ip", models.GenericIPAddressField(blank=True, null=True)),
                ("user_agent", models.CharField(blank=True, default="", max_length=500)),
                ("user", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="contact_changes", to=settings.AUTH_USER_MODEL)),
            ],
            options={
                "ordering": ["-requested_at"],
                "indexes": [
                    models.Index(fields=["user", "field", "status"], name="auth_users__user_id_3dc2f5_idx"),
                    models.Index(fields=["new_value", "field", "status"], name="auth_users__new_val_6b9df1_idx"),
                ],
            },
        ),
    ]
