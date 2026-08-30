# Generated manually for ServiceShare feature

from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion
import uuid


class Migration(migrations.Migration):

    dependencies = [
        ("services", "0011_alter_service_read_only"),
        ("messenger", "0014_participant_draft"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="ServiceShare",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "rules",
                    models.JSONField(
                        blank=True,
                        default=dict,
                        help_text="JSON map of allowed actions for recipients of this share.",
                        verbose_name="Permission Rules",
                    ),
                ),
                ("is_active", models.BooleanField(default=True, verbose_name="Active")),
                ("note", models.CharField(blank=True, default="", max_length=255, verbose_name="Note")),
                (
                    "group",
                    models.ForeignKey(
                        blank=True,
                        help_text="Messenger group this service is shared into.",
                        null=True,
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="shared_services",
                        to="messenger.conversation",
                        verbose_name="Shared with Group",
                    ),
                ),
                (
                    "service",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="shares",
                        to="services.service",
                        verbose_name="Service",
                    ),
                ),
                (
                    "shared_by",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="created_service_shares",
                        to=settings.AUTH_USER_MODEL,
                        verbose_name="Shared by",
                    ),
                ),
                (
                    "target_user",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="received_service_shares",
                        to=settings.AUTH_USER_MODEL,
                        verbose_name="Shared with User",
                    ),
                ),
            ],
            options={
                "verbose_name": "Service Share",
                "verbose_name_plural": "Service Shares",
            },
        ),
        migrations.CreateModel(
            name="ServiceShareEvent",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("action", models.CharField(max_length=64)),
                ("message", models.TextField(blank=True, default="")),
                ("metadata", models.JSONField(blank=True, default=dict)),
                (
                    "actor",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="+",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "share",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="events",
                        to="services.serviceshare",
                    ),
                ),
            ],
            options={
                "verbose_name": "Service Share Event",
                "verbose_name_plural": "Service Share Events",
                "ordering": ("-created_at",),
            },
        ),
        migrations.AddIndex(
            model_name="serviceshare",
            index=models.Index(fields=["service", "is_active"], name="services_se_service_8a1f0e_idx"),
        ),
        migrations.AddIndex(
            model_name="serviceshare",
            index=models.Index(fields=["group", "is_active"], name="services_se_group_i_6c2b1a_idx"),
        ),
        migrations.AddIndex(
            model_name="serviceshare",
            index=models.Index(fields=["target_user", "is_active"], name="services_se_target__9d3c2b_idx"),
        ),
        migrations.AddConstraint(
            model_name="serviceshare",
            constraint=models.CheckConstraint(
                check=(
                    models.Q(("group__isnull", False), ("target_user__isnull", True))
                    | models.Q(("group__isnull", True), ("target_user__isnull", False))
                ),
                name="service_share_exactly_one_target",
            ),
        ),
    ]
