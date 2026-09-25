from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion
import uuid


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("messenger", "0016_rename_messenger_ca_call_id_6fbf5a_idx_messenger_c_call_id_2067d1_idx_and_more"),
    ]

    operations = [
        migrations.AddField(
            model_name="message",
            name="client_message_id",
            field=models.CharField(
                blank=True,
                help_text="Client-generated idempotency key for message submission.",
                max_length=128,
                null=True,
            ),
        ),
        migrations.AddConstraint(
            model_name="message",
            constraint=models.UniqueConstraint(
                condition=models.Q(client_message_id__isnull=False, sender__isnull=False),
                fields=("conversation", "sender", "client_message_id"),
                name="uniq_message_client_operation",
            ),
        ),
        migrations.CreateModel(
            name="MessengerEvent",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("event_id", models.UUIDField(db_index=True, default=uuid.uuid4, editable=False, unique=True)),
                ("event_type", models.CharField(db_index=True, max_length=64)),
                ("payload", models.JSONField(blank=True, default=dict)),
                ("created_at", models.DateTimeField(auto_now_add=True, db_index=True)),
                ("actor", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="messenger_events", to=settings.AUTH_USER_MODEL)),
                ("conversation", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="messenger_events", to="messenger.conversation")),
                ("message", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="messenger_events", to="messenger.message")),
                ("call", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="messenger_events", to="messenger.callsession")),
            ],
            options={
                "ordering": ["created_at", "id"],
                "indexes": [
                    models.Index(fields=["conversation", "created_at", "id"], name="messenger_m_convers_cfa833_idx"),
                    models.Index(fields=["event_type", "created_at"], name="messenger_m_event_t_d711ef_idx"),
                ],
            },
        ),
    ]
