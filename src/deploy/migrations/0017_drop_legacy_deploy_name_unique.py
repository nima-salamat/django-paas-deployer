from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ("deploy", "0016_deploy_service_name"),
    ]

    operations = [
        migrations.RunSQL(
            sql=[
                "ALTER TABLE deploy_deploy DROP CONSTRAINT IF EXISTS deploy_deploy_name_key;",
                "DROP INDEX IF EXISTS deploy_deploy_name_key;",
            ],
            reverse_sql=migrations.RunSQL.noop,
        ),
    ]
