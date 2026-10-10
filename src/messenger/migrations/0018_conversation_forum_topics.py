from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        ("messenger", "0017_message_idempotency_messengerevent"),
    ]

    operations = [
        migrations.AddField(
            model_name="conversation",
            name="is_forum",
            field=models.BooleanField(db_index=True, default=False),
        ),
        migrations.AddField(
            model_name="conversation",
            name="parent_conversation",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name="topic_conversations",
                to="messenger.conversation",
            ),
        ),
    ]
