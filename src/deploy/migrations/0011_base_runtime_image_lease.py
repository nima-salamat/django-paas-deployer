from django.db import migrations, models
import uuid
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        ("deploy", "0010_base_runtime_image"),
    ]

    operations = [
        migrations.CreateModel(
            name="BaseRuntimeImageLease",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False, verbose_name="ID")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "deployment_id",
                    models.CharField(db_index=True, max_length=255),
                ),
                ("acquired_at", models.DateTimeField()),
                ("released_at", models.DateTimeField(blank=True, null=True)),
                (
                    "base_image",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="leases",
                        to="deploy.baseruntimeimage",
                    ),
                ),
            ],
            options={
                "verbose_name": "Base runtime image lease",
                "verbose_name_plural": "Base runtime image leases",
            },
        ),
        migrations.AddConstraint(
            model_name="baseruntimeimagelease",
            constraint=models.UniqueConstraint(
                fields=("base_image", "deployment_id"),
                name="uniq_base_image_deployment_lease",
            ),
        ),
        migrations.AddIndex(
            model_name="baseruntimeimagelease",
            index=models.Index(fields=("base_image", "released_at"), name="deploy_base_base_imag_lease_idx"),
        ),
    ]
