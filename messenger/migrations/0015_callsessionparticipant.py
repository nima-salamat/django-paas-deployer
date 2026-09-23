from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("messenger", "0014_participant_draft"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="CallSessionParticipant",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                ("joined_at", models.DateTimeField(auto_now_add=True)),
                ("left_at", models.DateTimeField(blank=True, null=True)),
                (
                    "call",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="participants",
                        to="messenger.callsession",
                    ),
                ),
                (
                    "user",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="messenger_call_participations",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={
                "constraints": [
                    models.UniqueConstraint(
                        fields=("call", "user"),
                        name="uniq_user_per_call_session",
                    )
                ],
                "indexes": [
                    models.Index(fields=("call", "left_at"), name="messenger_ca_call_id_6fbf5a_idx"),
                    models.Index(fields=("user", "left_at"), name="messenger_ca_user_id_a9f2f8_idx"),
                ],
            },
        ),
    ]
