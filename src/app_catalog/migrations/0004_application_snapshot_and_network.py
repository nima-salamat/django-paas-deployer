from django.db import migrations, models
import django.db.models.deletion


def populate_networks(apps, schema_editor):
    ApplicationInstance = apps.get_model("app_catalog", "ApplicationInstance")
    ApplicationInstanceService = apps.get_model("app_catalog", "ApplicationInstanceService")
    for instance in ApplicationInstance.objects.all().iterator():
        binding = (
            ApplicationInstanceService.objects
            .filter(instance_id=instance.pk)
            .select_related("service")
            .first()
        )
        network_id = getattr(getattr(binding, "service", None), "network_id", None)
        if network_id:
            ApplicationInstance.objects.filter(pk=instance.pk).update(network_id=network_id)


class Migration(migrations.Migration):
    dependencies = [("app_catalog", "0003_application_software_version")]

    operations = [
        migrations.AddField(
            model_name="applicationinstance",
            name="definition_snapshot",
            field=models.JSONField(blank=True, default=dict),
        ),
        migrations.AddField(
            model_name="applicationinstance",
            name="network",
            field=models.OneToOneField(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name="application_instance",
                to="services.privatenetwork",
            ),
        ),
        migrations.RunPython(populate_networks, migrations.RunPython.noop),
    ]
