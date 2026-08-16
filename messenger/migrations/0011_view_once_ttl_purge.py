from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        # After Django auto-renamed the long index from 0009
        ("messenger", "0010_rename_messenger_a_attachm_viewonce_idx_messenger_a_attachm_5536c2_idx"),
    ]

    operations = [
        migrations.AddField(
            model_name="messageattachment",
            name="is_purged",
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name="attachmentviewonceopen",
            name="expires_at",
            field=models.DateTimeField(blank=True, db_index=True, null=True),
        ),
    ]
