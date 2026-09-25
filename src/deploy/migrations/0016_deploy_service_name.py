from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("deploy", "0015_deploy_recovery_operation"),
    ]

    operations = [
        migrations.AlterField(
            model_name="deploy",
            name="name",
            field=models.CharField(max_length=50, verbose_name="Name"),
        ),
        migrations.AddConstraint(
            model_name="deploy",
            constraint=models.UniqueConstraint(
                fields=("service", "name"),
                name="uniq_deploy_service_name",
            ),
        ),
    ]
