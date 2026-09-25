from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("app_catalog", "0002_application_execution_state")]

    operations = [
        migrations.AddField(
            model_name="applicationinstance",
            name="software_version",
            field=models.CharField(default="unknown", max_length=64),
        ),
    ]
