"""
Adds:
  - Conversation.requires_approval (BooleanField — public groups can require admin approval to join)
  - JoinRequest model (Telegram-style — pending/approved/rejected join requests for public groups)
"""
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("messenger", "0004_bio_group_settings"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.AddField(
            model_name="conversation",
            name="requires_approval",
            field=models.BooleanField(default=False),
        ),
        migrations.CreateModel(
            name="JoinRequest",
            fields=[
                ("id", models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("status", models.CharField(
                    choices=[
                        ("pending", "Pending"),
                        ("approved", "Approved"),
                        ("rejected", "Rejected"),
                    ],
                    default="pending",
                    max_length=10,
                    db_index=True,
                )),
                ("decided_at", models.DateTimeField(blank=True, null=True)),
                ("created_at", models.DateTimeField(auto_now_add=True, db_index=True)),
                ("conversation", models.ForeignKey(
                    on_delete=models.CASCADE,
                    related_name="join_requests",
                    to="messenger.conversation",
                )),
                ("user", models.ForeignKey(
                    on_delete=models.CASCADE,
                    related_name="messenger_join_requests",
                    to=settings.AUTH_USER_MODEL,
                )),
                ("decided_by", models.ForeignKey(
                    blank=True,
                    null=True,
                    on_delete=models.SET_NULL,
                    related_name="messenger_join_requests_decided",
                    to=settings.AUTH_USER_MODEL,
                )),
            ],
            options={
                "indexes": [
                    models.Index(fields=["conversation", "status"], name="messenger_jr_conv_status_idx"),
                    models.Index(fields=["user", "status"], name="messenger_jr_user_status_idx"),
                ],
                "unique_together": {("conversation", "user", "status")},
            },
        ),
    ]
