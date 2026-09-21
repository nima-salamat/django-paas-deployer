from django.db import migrations, models
from django.core.validators import MaxValueValidator


class Migration(migrations.Migration):
    dependencies = [
        ("services", "0023_database_credential"),
    ]

    operations = [
        migrations.AlterField(
            model_name="serviceprocess",
            name="replicas",
            field=models.PositiveIntegerField(
                default=1,
                validators=[MaxValueValidator(1)],
            ),
        ),
    ]
