from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        ("app_catalog", "0008_alter_applicationinstance_network"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="CatalogPublication",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                (
                    "catalog_id",
                    models.CharField(max_length=64, unique=True),
                ),
                (
                    "enabled",
                    models.BooleanField(
                        default=True,
                        help_text="When disabled, hide this curated catalog entry from Ready Apps.",
                    ),
                ),
                (
                    "featured_override",
                    models.BooleanField(
                        blank=True,
                        help_text="Optional override for the catalog recipe's featured flag.",
                        null=True,
                    ),
                ),
                ("notes", models.TextField(blank=True, default="")),
                (
                    "created_at",
                    models.DateTimeField(auto_now_add=True),
                ),
                (
                    "updated_at",
                    models.DateTimeField(auto_now=True),
                ),
                (
                    "updated_by",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="+",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={"ordering": ("catalog_id",)},
        ),
    ]
