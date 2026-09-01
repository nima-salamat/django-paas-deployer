from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("deploy", "0012_base_runtime_build_task")]

    operations = [
        migrations.AddField(
            model_name="baseruntimeimage",
            name="build_owner_deployment_id",
            field=models.CharField(blank=True, default="", max_length=255),
        ),
    ]
