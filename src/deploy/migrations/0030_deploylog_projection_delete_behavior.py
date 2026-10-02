from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("deploy", "0029_detach_cross_database_log_relations"),
    ]

    operations = [
        migrations.AlterField(
            model_name="deploylog",
            name="deploy",
            field=models.ForeignKey(
                db_constraint=False,
                on_delete=models.DO_NOTHING,
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
                on_delete=models.DO_NOTHING,
                related_name="+",
                to="services.service",
                verbose_name="Service",
            ),
        ),
    ]
