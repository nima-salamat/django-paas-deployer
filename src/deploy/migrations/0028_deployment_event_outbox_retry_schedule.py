from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("deploy", "0027_deploylog_event_id")]
    operations = [
        migrations.AddField(
            model_name="deploymenteventoutbox",
            name="next_attempt_at",
            field=models.DateTimeField(blank=True, db_index=True, null=True),
        ),
    ]
