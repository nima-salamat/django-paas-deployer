from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("messenger", "0009_attachment_spoiler_view_once"),
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
