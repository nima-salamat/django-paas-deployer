from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion
import uuid


class Migration(migrations.Migration):

    dependencies = [
        ("services", "0013_serviceshare_expires_admin_preset"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="ServiceShareMember",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("rules", models.JSONField(blank=True, default=dict, help_text="Overrides parent share rules for this member only.", verbose_name="Permission Rules")),
                ("is_enabled", models.BooleanField(default=True, help_text="If false, this member has no access despite being in the group.", verbose_name="Enabled")),
                ("share", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="member_rules", to="services.serviceshare", verbose_name="Share")),
                ("user", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="service_share_member_rules", to=settings.AUTH_USER_MODEL, verbose_name="Member")),
            ],
            options={
                "verbose_name": "Service Share Member Rule",
                "verbose_name_plural": "Service Share Member Rules",
                "indexes": [models.Index(fields=["share", "user"], name="services_se_share_i_mem01_idx")],
                "unique_together": {("share", "user")},
            },
        ),
    ]
