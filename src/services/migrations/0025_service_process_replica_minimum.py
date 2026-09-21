from django.db import migrations, models
from django.core.validators import MinValueValidator, MaxValueValidator


class Migration(migrations.Migration):
    dependencies = [
        ("services", "0024_service_process_single_replica"),
    ]

    operations = [
        migrations.AlterField(
            model_name="serviceprocess",
            name="replicas",
            field=models.PositiveIntegerField(
                default=1,
                validators=[MinValueValidator(1), MaxValueValidator(1)],
            ),
        ),
    ]
