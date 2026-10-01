# Generated manually to keep DeployLog as a scalar-id projection
# rather than a cross-database reverse ORM relation.

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("deploy", "0028_deployment_event_outbox_retry_schedule"),
    ]

    operations = [
        migrations.AlterField(
            model_name="deploylog",
            name="deploy",
            field=models.ForeignKey(
                db_constraint=False,
                on_delete=models.CASCADE,
                related_name="+",
                to="deploy.deploy",
                verbose_name="Deploy",
            ),
        ),
        migrations.AlterField(
            model_name="deploylog",
            name="service",
            field=models.ForeignKey(
                db_constraint=False,
                on_delete=models.CASCADE,
                related_name="+",
                to="services.service",
                verbose_name="Service",
            ),
        ),
    ]
