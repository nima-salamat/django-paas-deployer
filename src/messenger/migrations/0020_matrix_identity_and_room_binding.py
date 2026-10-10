from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


def install_matrix_room_binding_trigger(apps, schema_editor):
    if schema_editor.connection.vendor != "postgresql":
        return
    with schema_editor.connection.cursor() as cursor:
        cursor.execute("""
            CREATE OR REPLACE FUNCTION messenger_reject_matrix_room_remap()
            RETURNS trigger AS $function$
            BEGIN
                IF NEW.security_mode IS DISTINCT FROM OLD.security_mode
                   OR NEW.matrix_room_id IS DISTINCT FROM OLD.matrix_room_id
                   OR NEW.matrix_space_id IS DISTINCT FROM OLD.matrix_space_id THEN
                    RAISE EXCEPTION
                        'Conversation security mode and Matrix room bindings are immutable';
                END IF;
                RETURN NEW;
            END;
            $function$ LANGUAGE plpgsql;
        """)
        cursor.execute("""
            DROP TRIGGER IF EXISTS messenger_conversation_matrix_binding_immutable
            ON messenger_conversation;
        """)
        cursor.execute("""
            CREATE TRIGGER messenger_conversation_matrix_binding_immutable
            BEFORE UPDATE OF security_mode, matrix_room_id, matrix_space_id
            ON messenger_conversation
            FOR EACH ROW
            EXECUTE FUNCTION messenger_reject_matrix_room_remap();
        """)


def remove_matrix_room_binding_trigger(apps, schema_editor):
    if schema_editor.connection.vendor != "postgresql":
        return
    with schema_editor.connection.cursor() as cursor:
        cursor.execute("""
            DROP TRIGGER IF EXISTS messenger_conversation_matrix_binding_immutable
            ON messenger_conversation;
        """)
        cursor.execute("DROP FUNCTION IF EXISTS messenger_reject_matrix_room_remap();")


class Migration(migrations.Migration):
    dependencies = [
        ("messenger", "0019_conversation_security_mode"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.AddField(
            model_name="conversation",
            name="matrix_room_id",
            field=models.CharField(blank=True, editable=False, max_length=255, null=True, unique=True),
        ),
        migrations.AddField(
            model_name="conversation",
            name="matrix_space_id",
            field=models.CharField(blank=True, editable=False, max_length=255, null=True),
        ),
        migrations.CreateModel(
            name="MatrixIdentity",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("matrix_user_id", models.CharField(db_index=True, max_length=255, unique=True)),
                ("encrypted_password", models.TextField()),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("user", models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, related_name="messenger_matrix_identity", to=settings.AUTH_USER_MODEL)),
            ],
        ),
        migrations.CreateModel(
            name="MatrixDevice",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("device_id", models.CharField(max_length=255)),
                ("display_name", models.CharField(blank=True, default="", max_length=100)),
                ("last_seen_at", models.DateTimeField(auto_now=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("revoked_at", models.DateTimeField(blank=True, db_index=True, null=True)),
                ("user", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="messenger_matrix_devices", to=settings.AUTH_USER_MODEL)),
            ],
            options={
                "ordering": ("-last_seen_at",),
                "constraints": [
                    models.UniqueConstraint(fields=("user", "device_id"), name="messenger_matrix_device_user_unique"),
                ],
            },
        ),
        migrations.AddConstraint(
            model_name="conversation",
            constraint=models.CheckConstraint(
                condition=(
                    models.Q(security_mode="standard", matrix_room_id__isnull=True, matrix_space_id__isnull=True)
                    | models.Q(security_mode="matrix_e2ee", matrix_room_id__isnull=False)
                ),
                name="messenger_conv_security_room_consistent",
            ),
        ),
        migrations.RunPython(
            install_matrix_room_binding_trigger,
            remove_matrix_room_binding_trigger,
        ),
    ]
