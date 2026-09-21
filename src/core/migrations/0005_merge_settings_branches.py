from django.db import migrations


class Migration(migrations.Migration):
    """Merge the URL-policy and operations settings branches.

    Both branches were created from 0002_core_settings. This merge migration
    deliberately performs no database operation; it only rejoins the graph
    without rewriting or deleting any previously applied migration.
    """

    dependencies = [
        ("core", "0003_core_settings_url_policy"),
        ("core", "0004_coresettings_mirrors_resources"),
    ]

    operations = []
