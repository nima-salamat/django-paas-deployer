from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("services", "0012_serviceshare_serviceshareevent"),
    ]

    operations = [
        migrations.AddField(
            model_name="serviceshare",
            name="expires_at",
            field=models.DateTimeField(
                blank=True,
                help_text="When set, share stops applying after this timestamp.",
                null=True,
                verbose_name="Expires at",
            ),
        ),
        migrations.AddField(
            model_name="serviceshare",
            name="admin_only",
            field=models.BooleanField(
                default=False,
                help_text="If set, only group owner/admin participants may exercise rules.",
                verbose_name="Admins only",
            ),
        ),
        migrations.AddField(
            model_name="serviceshare",
            name="preset",
            field=models.CharField(
                blank=True,
                default="",
                help_text="Optional preset name: viewer, operator, developer, ops.",
                max_length=32,
                verbose_name="Preset",
            ),
        ),
    ]
