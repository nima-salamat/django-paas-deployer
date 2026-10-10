from django.db import migrations, models


def install_security_mode_triggers(apps, schema_editor):
    """
    Enforce immutable security mode and block plaintext rows at the database
    boundary. This protects bulk_create and other ORM paths that bypass save().
    """
    if schema_editor.connection.vendor != "postgresql":
        return

    with schema_editor.connection.cursor() as cursor:
        cursor.execute("""
            CREATE OR REPLACE FUNCTION messenger_reject_security_mode_change()
            RETURNS trigger AS $function$
            BEGIN
                IF NEW.security_mode IS DISTINCT FROM OLD.security_mode THEN
                    RAISE EXCEPTION
                        'Conversation security_mode is immutable; create a separate conversation';
                END IF;
                RETURN NEW;
            END;
            $function$ LANGUAGE plpgsql;
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

        cursor.execute("""
            CREATE OR REPLACE FUNCTION messenger_reject_plaintext_draft_for_e2ee_conversation()
            RETURNS trigger AS $function$
            DECLARE current_security_mode varchar(20);
            BEGIN
                IF COALESCE(NEW.draft_text, '') <> '' THEN
                    SELECT security_mode
                      INTO current_security_mode
                      FROM messenger_conversation
                     WHERE id = NEW.conversation_id;

                    IF current_security_mode = 'matrix_e2ee' THEN
                        RAISE EXCEPTION
                            'Server-side composer drafts are disabled for Matrix E2EE conversations';
                    END IF;
                END IF;
                RETURN NEW;
            END;
            $function$ LANGUAGE plpgsql;
        """)
        cursor.execute("""
            DROP TRIGGER IF EXISTS messenger_participant_no_plaintext_draft_for_e2ee
            ON messenger_conversationparticipant;
        """)
        cursor.execute("""
            CREATE TRIGGER messenger_participant_no_plaintext_draft_for_e2ee
            BEFORE INSERT OR UPDATE ON messenger_conversationparticipant
            FOR EACH ROW
            EXECUTE FUNCTION messenger_reject_plaintext_draft_for_e2ee_conversation();
        """)

        cursor.execute("""
            CREATE OR REPLACE FUNCTION messenger_reject_plaintext_for_e2ee_conversation()
            RETURNS trigger AS $function$
            DECLARE current_security_mode varchar(20);
            BEGIN
                IF TG_OP = 'UPDATE' THEN
                    SELECT security_mode
                      INTO current_security_mode
                      FROM messenger_conversation
                     WHERE id = OLD.conversation_id;

                    IF current_security_mode = 'matrix_e2ee' THEN
                        RAISE EXCEPTION
                            'Plaintext Messenger records are disabled for Matrix E2EE conversations';
                    END IF;
                END IF;

                SELECT security_mode
                  INTO current_security_mode
                  FROM messenger_conversation
                 WHERE id = NEW.conversation_id;

                IF current_security_mode = 'matrix_e2ee' THEN
                    RAISE EXCEPTION
                        'Plaintext Messenger records are disabled for Matrix E2EE conversations';
                END IF;
                RETURN NEW;
            END;
            $function$ LANGUAGE plpgsql;
        """)
        cursor.execute("""
            DROP TRIGGER IF EXISTS messenger_message_no_plaintext_for_e2ee
            ON messenger_message;
        """)
        cursor.execute("""
            CREATE TRIGGER messenger_message_no_plaintext_for_e2ee
            BEFORE INSERT OR UPDATE ON messenger_message
            FOR EACH ROW
            EXECUTE FUNCTION messenger_reject_plaintext_for_e2ee_conversation();
        """)
        cursor.execute("""
            DROP TRIGGER IF EXISTS messenger_attachment_no_plaintext_for_e2ee
            ON messenger_messageattachment;
        """)
        cursor.execute("""
            CREATE TRIGGER messenger_attachment_no_plaintext_for_e2ee
            BEFORE INSERT OR UPDATE ON messenger_messageattachment
            FOR EACH ROW
            EXECUTE FUNCTION messenger_reject_plaintext_for_e2ee_conversation();
        """)


def remove_security_mode_triggers(apps, schema_editor):
    if schema_editor.connection.vendor != "postgresql":
        return

    with schema_editor.connection.cursor() as cursor:
        cursor.execute("""
            DROP TRIGGER IF EXISTS messenger_conversation_security_mode_immutable
            ON messenger_conversation;
        """)
        cursor.execute("""
            DROP TRIGGER IF EXISTS messenger_message_no_plaintext_for_e2ee
            ON messenger_message;
        """)
        cursor.execute("""
            DROP TRIGGER IF EXISTS messenger_attachment_no_plaintext_for_e2ee
            ON messenger_messageattachment;
        """)
        cursor.execute("""
            DROP FUNCTION IF EXISTS messenger_reject_security_mode_change();
        """)
        cursor.execute("""
            DROP FUNCTION IF EXISTS messenger_reject_plaintext_for_e2ee_conversation();
        """)
        cursor.execute("""
            DROP TRIGGER IF EXISTS messenger_participant_no_plaintext_draft_for_e2ee
            ON messenger_conversationparticipant;
        """)
        cursor.execute("""
            DROP FUNCTION IF EXISTS messenger_reject_plaintext_draft_for_e2ee_conversation();
        """)


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
            install_security_mode_triggers,
            remove_security_mode_triggers,
        ),
    ]
