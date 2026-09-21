from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("messenger", "0013_call_active_unique"),
    ]

    operations = [
        migrations.AddField(
            model_name="conversationparticipant",
            name="draft_text",
            field=models.TextField(blank=True, default=""),
        ),
        migrations.AddField(
            model_name="conversationparticipant",
            name="draft_updated_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
    ]
