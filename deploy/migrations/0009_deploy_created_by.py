from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("deploy", "0008_deploylog_event_metadata"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.AddField(
            model_name="deploy",
            name="created_by",
            field=models.ForeignKey(
                blank=True,
                help_text="User who uploaded this deploy (for share permission scoping).",
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="created_deploys",
                to=settings.AUTH_USER_MODEL,
                verbose_name="Created by",
            ),
        ),
    ]
