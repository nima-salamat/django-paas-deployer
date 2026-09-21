from django.db import migrations


class Migration(migrations.Migration):
    """Final no-op merge for deployments that already contain both legacy leaves."""

    dependencies = [
        ("core", "0005_merge_settings_branches"),
        ("core", "0008_merge_core_settings_shell"),
    ]

    operations = []
