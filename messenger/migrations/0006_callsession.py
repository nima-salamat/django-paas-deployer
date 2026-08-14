# Generated manually for CallSession

from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion
import uuid


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("messenger", "0005_join_requests"),
    ]

    operations = [
        migrations.CreateModel(
            name="CallSession",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("public_id", models.UUIDField(db_index=True, default=uuid.uuid4, editable=False, unique=True)),
                ("is_video", models.BooleanField(default=False)),
                ("status", models.CharField(
                    choices=[
                        ("ringing", "Ringing"),
                        ("active", "Active"),
                        ("ended", "Ended"),
                        ("missed", "Missed"),
                        ("declined", "Declined"),
                        ("no_answer", "No answer"),
                    ],
                    db_index=True,
                    default="ringing",
                    max_length=16,
                )),
                ("room_name", models.CharField(blank=True, default="", max_length=120)),
                ("started_at", models.DateTimeField(auto_now_add=True)),
                ("answered_at", models.DateTimeField(blank=True, null=True)),
                ("ended_at", models.DateTimeField(blank=True, null=True)),
                ("duration_seconds", models.PositiveIntegerField(default=0)),
                ("conversation", models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name="call_sessions",
                    to="messenger.conversation",
                )),
                ("end_message", models.ForeignKey(
                    blank=True,
                    null=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    related_name="+",
                    to="messenger.message",
                )),
                ("initiator", models.ForeignKey(
                    null=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    related_name="messenger_calls_started",
                    to=settings.AUTH_USER_MODEL,
                )),
                ("start_message", models.ForeignKey(
                    blank=True,
                    null=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    related_name="+",
                    to="messenger.message",
                )),
            ],
            options={
                "ordering": ["-started_at"],
            },
        ),
        migrations.AddIndex(
            model_name="callsession",
            index=models.Index(fields=["conversation", "status"], name="messenger_c_convers_status_idx"),
        ),
        migrations.AddIndex(
            model_name="callsession",
            index=models.Index(fields=["conversation", "-started_at"], name="messenger_c_convers_started_idx"),
        ),
    ]
