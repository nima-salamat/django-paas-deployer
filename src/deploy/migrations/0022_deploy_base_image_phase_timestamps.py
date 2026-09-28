from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("deploy", "0021_base_runtime_definition_and_error_details"),
    ]

    operations = [
        migrations.AddField(
            model_name="deploy",
            name="base_image_wait_started_at",
            field=models.DateTimeField(blank=True, null=True, editable=False, verbose_name="Base Image Wait Started", help_text="Start of this deployment's dedicated base-image build/wait phase."),
        ),
        migrations.AddField(
            model_name="deploy",
            name="base_image_ready_at",
            field=models.DateTimeField(blank=True, null=True, editable=False, verbose_name="Base Image Ready", help_text="Timestamp when all required base runtime images became available."),
        ),
        migrations.AddField(
            model_name="deploy",
            name="application_started_at",
            field=models.DateTimeField(blank=True, null=True, editable=False, verbose_name="Application Phase Started", help_text="Start of the normal application deployment budget after base images are ready."),
        ),
    ]