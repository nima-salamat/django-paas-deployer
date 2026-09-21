from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("messenger", "0006_callsession_and_more"),
    ]

    operations = [
        migrations.AddField(
            model_name="message",
            name="scheduled_for",
            field=models.DateTimeField(blank=True, db_index=True, null=True),
        ),
        migrations.AddField(
            model_name="message",
            name="is_scheduled",
            field=models.BooleanField(db_index=True, default=False),
        ),
        migrations.AddIndex(
            model_name="message",
            index=models.Index(fields=["is_scheduled", "scheduled_for"], name="messenger_m_is_sche_idx"),
        ),
    ]
