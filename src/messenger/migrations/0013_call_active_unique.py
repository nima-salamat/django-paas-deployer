from django.db import migrations, models
from django.db.models import Q


class Migration(migrations.Migration):
    dependencies = [
        ("messenger", "0012_merge_view_once"),
    ]

    operations = [
        migrations.AddConstraint(
            model_name="callsession",
            constraint=models.UniqueConstraint(
                fields=("conversation",),
                condition=Q(status__in=["ringing", "active"]),
                name="uniq_active_call_per_conversation",
            ),
        ),
    ]
