from django.db import migrations


class Migration(migrations.Migration):
    """Merge parallel view-once migration branches.

    Leaves were:
      - 0010_view_once_ttl_purge  (adds is_purged + expires_at)
      - 0011_view_once_ttl_purge  (same fields, other parent)
    This merge unifies the graph. Field adds live only in 0010_view_once_ttl_purge.
    """

    dependencies = [
        ("messenger", "0010_view_once_ttl_purge"),
        ("messenger", "0011_view_once_ttl_purge"),
    ]

    operations = []
