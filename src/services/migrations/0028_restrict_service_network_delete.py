from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("services", "0027_rename_service_port_res_host_protocol_state_services_se_host_po_f50e1a_idx_and_more"),
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
