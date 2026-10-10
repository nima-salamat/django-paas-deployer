from django.db import migrations, models


def install_security_mode_immutability_trigger(apps, schema_editor):
    """Enforce the immutable security boundary in PostgreSQL as well as ORM saves."""
    if schema_editor.connection.vendor != "postgresql":
        return
    with schema_editor.connection.cursor() as cursor:
        cursor.execute("""
            CREATE OR REPLACE FUNCTION messenger_reject_security_mode_change()
            RETURNS trigger AS $
            BEGIN
                IF NEW.security_mode IS DISTINCT FROM OLD.security_mode THEN
                    RAISE EXCEPTION
                        'Conversation security_mode is immutable; create a separate conversation';
                END IF;
                RETURN NEW;
            END;
            $ LANGUAGE plpgsql;
        """)
        cursor.execute("""
            DROP TRIGGER IF EXISTS messenger_conversation_security_mode_immutable
            ON messenger_conversation;
        """)
        cursor.execute("""
            CREATE TRIGGER messenger_conversation_security_mode_immutable
            BEFORE UPDATE OF security_mode ON messenger_conversation
            FOR EACH ROW
            EXECUTE FUNCTION messenger_reject_security_mode_change();
        """)


def remove_security_mode_immutability_trigger(apps, schema_editor):
    if schema_editor.connection.vendor != "postgresql":
        return
    with schema_editor.connection.cursor() as cursor:
        cursor.execute("""
            DROP TRIGGER IF EXISTS messenger_conversation_security_mode_immutable
            ON messenger_conversation;
        """)
        cursor.execute("DROP FUNCTION IF EXISTS messenger_reject_security_mode_change();")


class Migration(migrations.Migration):
    dependencies = [
        ("messenger", "0018_conversation_forum_topics"),
    ]

    operations = [
        migrations.AddField(
            model_name="conversation",
            name="security_mode",
            field=models.CharField(
                choices=[
                    ("standard", "Standard chat"),
                    ("matrix_e2ee", "End-to-end encrypted (Matrix)"),
                ],
                db_index=True,
                default="standard",
                max_length=20,
            ),
        ),
        migrations.RunPython(
            install_security_mode_immutability_trigger,
            remove_security_mode_immutability_trigger,
        ),
    ]
