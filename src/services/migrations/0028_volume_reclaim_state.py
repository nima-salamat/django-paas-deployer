from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("services", "0027_volume_released_at")]

    operations = [
        migrations.AddField(
            model_name="volume",
            name="reclaim_attempted_at",
            field=models.DateTimeField(blank=True, editable=False, null=True, verbose_name="Reclaim Attempted At"),
        ),
        migrations.AddField(
            model_name="volume",
            name="reclaim_error",
            field=models.TextField(blank=True, default="", editable=False, verbose_name="Reclaim Error"),
        ),
    ]
