from django.db import migrations, models


def backfill_installation_graph(apps, schema_editor):
    ApplicationInstance = apps.get_model("app_catalog", "ApplicationInstance")
    ApplicationInstanceService = apps.get_model("app_catalog", "ApplicationInstanceService")

    for instance in ApplicationInstance.objects.all().iterator():
        snapshot = dict(instance.definition_snapshot or {})
        if snapshot.get("_application_orchestration", {}).get("services"):
            continue

        services = []
        rows = ApplicationInstanceService.objects.filter(instance_id=instance.pk).select_related("service")
        for row in rows.order_by("sequence", "service_key"):
            runtime = dict(row.service.runtime_config or {})
            services.append({
                "key": str(row.service_key),
                "role": "database" if str(runtime.get("catalog_plan_type") or "") == "DB" else "app",
                "platform": str(runtime.get("catalog_platform") or "docker"),
                "plan_type": str(runtime.get("catalog_plan_type") or "APP"),
                "depends_on": [str(dep) for dep in (runtime.get("depends_on") or [])],
                "required": bool(runtime.get("required", True)),
            })
        if services:
            snapshot["_application_orchestration"] = {"services": services}
            ApplicationInstance.objects.filter(pk=instance.pk).update(definition_snapshot=snapshot)


class Migration(migrations.Migration):

    dependencies = [
        ("app_catalog", "0005_alter_applicationinstance_stage"),
    ]

    operations = [
        migrations.RunPython(backfill_installation_graph, migrations.RunPython.noop),
        migrations.AlterField(
            model_name="applicationinstanceservice",
            name="service",
            field=models.OneToOneField(
                on_delete=models.PROTECT,
                related_name="application_binding",
                to="services.service",
            ),
        ),
        migrations.AlterField(
            model_name="applicationinstanceservice",
            name="deploy",
            field=models.OneToOneField(
                on_delete=models.PROTECT,
                related_name="application_binding",
                to="deploy.deploy",
            ),
        ),
    ]
