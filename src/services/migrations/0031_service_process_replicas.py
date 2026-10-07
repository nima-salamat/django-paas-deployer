from django.db import migrations, models
from django.core.validators import MinValueValidator, MaxValueValidator


class Migration(migrations.Migration):
    dependencies = [
        ("services", "0030_shell_session_mode"),
    ]

    operations = [
        migrations.AlterField(
            model_name="serviceprocess",
            name="replicas",
            field=models.PositiveIntegerField(
                default=1,
                validators=[MinValueValidator(1), MaxValueValidator(8)],
            ),
        ),
    ]
