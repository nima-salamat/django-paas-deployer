from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("messenger", "0018_conversation_forum_topics"),
    ]

    operations = [
        migrations.AddField(
            model_name="conversation",
            name="security_mode",
            field=models.CharField(
                choices=[
                    ("standard", "Standard chat"),
                    ("matrix_e2ee", "End-to-end encrypted (Matrix)"),
                ],
                db_index=True,
                default="standard",
                max_length=20,
            ),
        ),
    ]
