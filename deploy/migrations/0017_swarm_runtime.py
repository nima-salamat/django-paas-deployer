from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        ("deploy", "0016_deploy_revision"),
    ]

    operations = [
        migrations.CreateModel(
            name="SwarmCluster",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("name", models.CharField(default="default", max_length=128, unique=True)),
                ("enabled", models.BooleanField(default=True)),
                ("manager_endpoint", models.CharField(blank=True, default="", help_text="Informational Docker manager endpoint. Credentials are never stored here.", max_length=255)),
                ("last_synced_at", models.DateTimeField(blank=True, null=True)),
                ("last_error", models.TextField(blank=True, default="")),
            ],
            options={
                "verbose_name": "Docker Swarm cluster",
                "verbose_name_plural": "Docker Swarm clusters",
            },
        ),
        migrations.CreateModel(
            name="SwarmNode",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("docker_id", models.CharField(max_length=128, unique=True)),
                ("hostname", models.CharField(max_length=255)),
                ("role", models.CharField(blank=True, default="", max_length=16)),
                ("desired_availability", models.CharField(choices=[("active", "Active"), ("pause", "Pause"), ("drain", "Drain")], default="active", max_length=16)),
                ("observed_availability", models.CharField(blank=True, default="", max_length=16)),
                ("observed_state", models.CharField(blank=True, default="", max_length=32)),
                ("address", models.CharField(blank=True, default="", max_length=255)),
                ("labels", models.JSONField(blank=True, default=dict)),
                ("desired_labels", models.JSONField(blank=True, default=dict)),
                ("cpus", models.PositiveIntegerField(default=0)),
                ("memory_bytes", models.BigIntegerField(default=0)),
                ("manager_reachable", models.BooleanField(default=False)),
                ("last_synced_at", models.DateTimeField(blank=True, null=True)),
                ("last_error", models.TextField(blank=True, default="")),
                ("cluster", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="nodes", to="deploy.swarmcluster")),
            ],
            options={
                "verbose_name": "Docker Swarm node",
                "verbose_name_plural": "Docker Swarm nodes",
                "ordering": ("hostname",),
                "constraints": [
                    models.UniqueConstraint(fields=("cluster", "hostname"), name="uniq_swarm_cluster_node_hostname"),
                ],
            },
        ),
    ]
