from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("messenger", "0008_rename_messenger_m_is_sche_idx_messenger_m_is_sche_79ff54_idx"),
    ]

    operations = [
        migrations.AddField(
            model_name="messageattachment",
            name="is_spoiler",
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name="messageattachment",
            name="is_view_once",
            field=models.BooleanField(default=False),
        ),
        migrations.CreateModel(
            name="AttachmentViewOnceOpen",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("opened_at", models.DateTimeField(auto_now_add=True)),
                (
                    "attachment",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="view_once_opens",
                        to="messenger.messageattachment",
                    ),
                ),
                (
                    "user",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="view_once_opens",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={
                "unique_together": {("attachment", "user")},
            },
        ),
        migrations.AddIndex(
            model_name="attachmentviewonceopen",
            index=models.Index(fields=["attachment", "user"], name="messenger_a_attachm_viewonce_idx"),
        ),
    ]
