from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("core", "0001_initial"),
    ]

    operations = [
        migrations.CreateModel(
            name="CoreSettings",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                (
                    "base_images_enabled",
                    models.BooleanField(
                        default=True,
                        help_text="Reuse registered PHP, Python, Node and other runtime base images during deployment.",
                        verbose_name="Use base runtime image cache",
                    ),
                ),
                (
                    "base_images_auto_build",
                    models.BooleanField(
                        default=True,
                        help_text="Build a requested runtime base image automatically when it is not available on the Docker host.",
                        verbose_name="Auto-build missing base images",
                    ),
                ),
                (
                    "base_images_retain_after_deploy",
                    models.BooleanField(
                        default=True,
                        help_text="When disabled, an unused base image is removed after the deployment releases its lease. Shared images are kept until no active deployment uses them.",
                        verbose_name="Keep base images after deployment",
                    ),
                ),
                (
                    "base_images_auto_register_existing",
                    models.BooleanField(
                        default=True,
                        help_text="Adopt matching runtime images already present on the Docker host instead of rebuilding them.",
                        verbose_name="Register existing Docker images",
                    ),
                ),
            ],
            options={
                "verbose_name": "Core / Deployment settings",
                "verbose_name_plural": "Core / Deployment settings",
            },
        ),
    ]
