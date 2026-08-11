"""
Adds:
  - UserBio model (per-user 'about' text — Messenger-owned)
  - Conversation.only_admins_send (channel-like mode)
  - Conversation.history_visibility (all / from_join / none for new members)
"""
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("messenger", "0003_participant_pin_readreceipt"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="UserBio",
            fields=[
                ("id", models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("text", models.CharField(blank=True, default="", max_length=255)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("user", models.OneToOneField(
                    on_delete=models.CASCADE,
                    related_name="messenger_bio",
                    to=settings.AUTH_USER_MODEL,
                )),
            ],
        ),
        migrations.AddField(
            model_name="conversation",
            name="only_admins_send",
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name="conversation",
            name="history_visibility",
            field=models.CharField(
                max_length=12,
                choices=[
                    ("all", "All new members see history"),
                    ("from_join", "Only messages from join-time onward"),
                    ("none", "No history for new members"),
                ],
                default="all",
            ),
        ),
    ]
