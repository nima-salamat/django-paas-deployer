from django.test import TestCase

from custom_emails.models import EmailLog, EmailTemplate
from users.models import User


class CustomEmailUserDeletionTests(TestCase):
    def test_email_history_survives_user_deletion_with_null_actor_links(self):
        user = User.objects.create_user(
            username="email-delete",
            email="email-delete@example.invalid",
        )
        template = EmailTemplate.objects.create(
            name="deleted-user-template",
            subject="Hello",
            body="Hello {{ user.username }}",
            created_by=user,
        )
        log = EmailLog.objects.create(
            recipient=user,
            recipient_email=user.email,
            template=template,
            subject="Audit copy",
            sent_by=user,
        )

        user.delete()

        template.refresh_from_db()
        log.refresh_from_db()
        self.assertIsNone(template.created_by_id)
        self.assertIsNone(log.recipient_id)
        self.assertIsNone(log.sent_by_id)
        self.assertEqual(log.recipient_email, "email-delete@example.invalid")
        self.assertTrue(EmailLog.objects.filter(pk=log.pk).exists())
