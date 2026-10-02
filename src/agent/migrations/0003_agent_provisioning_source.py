from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("agent", "0002_align_basemodel_indexes_and_scopes"),
    ]

    operations = [
        migrations.AddField(
            model_name="agent",
            name="provisioning_source",
            field=models.CharField(
                choices=[
                    ("dashboard", "Dashboard"),
                    ("api_enrollment", "API enrollment"),
                    ("legacy", "Legacy / unspecified"),
                ],
                db_index=True,
                default="legacy",
                max_length=24,
            ),
        ),
    ]
