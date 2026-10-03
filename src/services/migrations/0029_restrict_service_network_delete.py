from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("services", "0028_volume_reclaim_state"),
    ]

    operations = [
        migrations.AlterField(
            model_name="service",
            name="network",
            field=models.ForeignKey(
                null=True,
                on_delete=models.RESTRICT,
                related_name="Service",
                to="services.privatenetwork",
                verbose_name="Private Network",
            ),
        ),
    ]
