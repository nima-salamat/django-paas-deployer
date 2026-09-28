from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [\n        ("services", "0027_rename_service_port_res_host_protocol_state_services_se_host_po_f50e1a_idx_and_more"),\n        ("services", "0027_volume_released_at"),\n    ]

    operations = [
        migrations.AddField(
            model_name="volume",
            name="reclaim_attempted_at",
            field=models.DateTimeField(blank=True, editable=False, null=True, verbose_name="Reclaim Attempted At"),
        ),
        migrations.AddField(
            model_name="volume",
            name="reclaim_error",
            field=models.TextField(blank=True, default="", editable=False, verbose_name="Reclaim Error"),
        ),
    ]
