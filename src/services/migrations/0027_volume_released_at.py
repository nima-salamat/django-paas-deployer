from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("services", "0026_service_lifecycle_generation")]

    operations = [
        migrations.AddField(
            model_name="volume",
            name="released_at",
            field=models.DateTimeField(blank=True, db_index=True, help_text="When logical Service ownership was released while the Docker volume remained physically retained.", null=True, verbose_name="Released At"),
        ),
    ]