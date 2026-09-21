from django.db import migrations


class Migration(migrations.Migration):
    """Bridge on the rename branch — real fields are in 0010_view_once_ttl_purge.

    Kept so containers that already recorded 0011 in django_migrations stay valid.
    New field work is done once via 0010_view_once_ttl_purge; 0012 merges both leaves.
    """

    dependencies = [
        ("messenger", "0010_rename_messenger_a_attachm_viewonce_idx_messenger_a_attachm_5536c2_idx"),
    ]

    operations = []
