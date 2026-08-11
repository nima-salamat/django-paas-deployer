"""
Adds is_pinned / pinned_at to ConversationParticipant
and creates MessageReadReceipt model for per-message seen tracking.
"""
from django.conf import settings
from django.db import migrations, models
import django.utils.timezone


class Migration(migrations.Migration):

    dependencies = [
        ("messenger", "0002_block_contact_conversationparticipant_and_more"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.AddField(
            model_name="conversationparticipant",
            name="is_pinned",
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name="conversationparticipant",
            name="pinned_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddIndex(
            model_name="conversationparticipant",
            index=models.Index(fields=["user", "is_pinned"], name="messenger_cp_user_pin_idx"),
        ),
        migrations.CreateModel(
            name="MessageReadReceipt",
            fields=[
                ("id", models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("seen_at", models.DateTimeField(auto_now_add=True)),
                ("message", models.ForeignKey(on_delete=models.CASCADE, related_name="read_receipts", to="messenger.message")),
                ("user", models.ForeignKey(on_delete=models.CASCADE, related_name="messenger_read_receipts", to=settings.AUTH_USER_MODEL)),
            ],
            options={
                "unique_together": {("message", "user")},
                "indexes": [models.Index(fields=["message", "user"], name="messenger_mrr_msg_user_idx")],
            },
        ),
    ]
