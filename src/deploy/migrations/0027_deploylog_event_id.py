from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("deploy", "0026_deployment_lifecycle_journal")]
    operations = [
        migrations.AddField(
            model_name="deploylog",
            name="event_id",
            field=models.UUIDField(blank=True, db_index=True, null=True, unique=True),
        ),
    ]
