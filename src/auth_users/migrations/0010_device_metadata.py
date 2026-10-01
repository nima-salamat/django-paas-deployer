from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("auth_users", "0009_usercontactchange_contact_change_purpose"),
    ]

    operations = [
        migrations.AddField(
            model_name="device",
            name="metadata",
            field=models.JSONField(blank=True, default=dict),
        ),
    ]
