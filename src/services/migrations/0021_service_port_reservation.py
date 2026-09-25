from django.db import migrations, models
import django.db.models.deletion
from django.db.models import Q
from uuid import uuid4


class Migration(migrations.Migration):
    dependencies = [
        ("services", "0020_revision_runtime_graph"),
    ]

    operations = [
        migrations.CreateModel(
            name="ServicePortReservation",
            fields=[
                ("id", models.UUIDField(default=uuid4, editable=False, primary_key=True, serialize=False)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("host_port", models.PositiveIntegerField()),
                ("protocol", models.CharField(default="tcp", max_length=8)),
                ("state", models.CharField(choices=[("active", "Active"), ("released", "Released")], default="active", max_length=16)),
                ("metadata", models.JSONField(blank=True, default=dict)),
                (
                    "endpoint",
                    models.OneToOneField(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="port_reservation",
                        to="services.serviceendpoint",
                    ),
                ),
                (
                    "service",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="port_reservations",
                        to="services.service",
                    ),
                ),
            ],
            options={
                "constraints": [
                    models.UniqueConstraint(
                        condition=Q(state="active"),
                        fields=("host_port", "protocol"),
                        name="uniq_active_host_port_protocol",
                    )
                ],
                "indexes": [
                    models.Index(
                        fields=("host_port", "protocol", "state"),
                        name="service_port_res_host_protocol_state",
                    ),
                ],
            },
        ),
    ]
