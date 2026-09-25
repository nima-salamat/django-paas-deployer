from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("deploy", "0011_base_runtime_image_lease")]

    operations = [
        migrations.AddField(
            model_name="baseruntimeimage",
            name="build_task_id",
            field=models.CharField(blank=True, default="", max_length=255),
        ),
    ]
