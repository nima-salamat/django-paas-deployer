from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("app_catalog", "0006_installation_graph_and_binding_protection"),
    ]

    operations = [
        migrations.AlterField(
            model_name="applicationinstanceservice",
            name="service",
            field=models.OneToOneField(
                on_delete=models.RESTRICT,
                related_name="application_binding",
                to="services.service",
            ),
        ),
        migrations.AlterField(
            model_name="applicationinstanceservice",
            name="deploy",
            field=models.OneToOneField(
                on_delete=models.RESTRICT,
                related_name="application_binding",
                to="deploy.deploy",
            ),
        ),
    ]
