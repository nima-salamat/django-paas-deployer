from django.db import migrations, models
import uuid


class Migration(migrations.Migration):

    dependencies = [
        ("auth_users", "0009_usercontactchange_contact_change_purpose"),
    ]

    operations = [
        migrations.AlterField(
            model_name="device",
            name="public_id",
            field=models.UUIDField(db_index=True, default=uuid.uuid4, editable=False),
        ),
        migrations.AddConstraint(
            model_name="device",
            constraint=models.UniqueConstraint(
                fields=("user", "public_id"),
                name="auth_device_user_public_id_uniq",
            ),
        ),
    ]
