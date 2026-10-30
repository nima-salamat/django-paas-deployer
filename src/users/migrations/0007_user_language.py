from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("users", "0006_user_deletion_requested_at"),
    ]

    operations = [
        migrations.AddField(
            model_name="user",
            name="language",
            field=models.CharField(
                choices=[("en-us", "English"), ("fa", "Persian")],
                default="en-us",
                max_length=5,
                verbose_name="preferred language",
            ),
        ),
    ]
