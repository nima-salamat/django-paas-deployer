from django.db import migrations, models
import django.db.models.deletion
from uuid import uuid4


class Migration(migrations.Migration):
    dependencies = [
        ("services", "0022_revision_artifact"),
    ]

    operations = [
        migrations.CreateModel(
            name="DatabaseCredential",
            fields=[
                ("id", models.UUIDField(default=uuid4, editable=False, primary_key=True, serialize=False)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("username", models.CharField(blank=True, default="", max_length=128)),
                ("password_ciphertext", models.TextField(blank=True, default="")),
                ("version", models.PositiveIntegerField(default=1)),
                (
                    "database",
                    models.OneToOneField(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="credential",
                        to="services.databaseresource",
                    ),
                ),
            ],
        ),
    ]
