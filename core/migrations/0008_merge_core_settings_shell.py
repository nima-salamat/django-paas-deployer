from django.db import migrations


class Migration(migrations.Migration):
    """Reconcile all CoreSettings migration branches from older releases."""

    dependencies = [
        ("core", "0005_merge_core_settings"),
        ("core", "0007_merge_settings_shell_branches"),
    ]

    operations = []
