from pathlib import Path
from tempfile import TemporaryDirectory

from django.test import TestCase, override_settings
from django.core.files.uploadedfile import SimpleUploadedFile

from tickets.models import Department, Ticket, TicketAttachment, TicketMessage, TicketReadState
from users.models import User


class TicketUserDeletionTests(TestCase):
    def test_ticket_data_and_attachment_media_follow_ticket_ownership(self):
        user = User.objects.create_user(
            username="ticket-delete",
            email="ticket-delete@example.invalid",
        )
        staff = User.objects.create_user(
            username="ticket-staff",
            email="ticket-staff@example.invalid",
        )
        department = Department.objects.create(name="Delete Test")
        ticket = Ticket.objects.create(
            user=user,
            assigned_to=staff,
            department=department,
            subject="Delete me",
        )
        message = TicketMessage.objects.create(
            ticket=ticket,
            author=staff,
            body="staff reply",
            is_staff_reply=True,
        )
        read_state = TicketReadState.objects.create(ticket=ticket, user=user)

        with TemporaryDirectory() as media_root, override_settings(MEDIA_ROOT=media_root):
            attachment = TicketAttachment.objects.create(
                ticket=ticket,
                message=message,
                uploaded_by=user,
                file=SimpleUploadedFile("evidence.txt", b"ticket-evidence"),
                original_filename="evidence.txt",
            )
            path = Path(attachment.file.path)
            self.assertTrue(path.exists())

            user.delete()

            self.assertFalse(path.exists())

        self.assertFalse(Ticket.objects.filter(pk=ticket.pk).exists())
        self.assertFalse(TicketMessage.objects.filter(pk=message.pk).exists())
        self.assertFalse(TicketReadState.objects.filter(pk=read_state.pk).exists())
        staff.refresh_from_db()
        self.assertTrue(User.objects.filter(pk=staff.pk).exists())

    def test_attachment_storage_failure_blocks_ticket_deletion(self):
        user = User.objects.create_user(
            username="ticket-storage-failure",
            email="ticket-storage-failure@example.invalid",
        )
        department = Department.objects.create(name="Storage Failure")
        ticket = Ticket.objects.create(
            user=user,
            department=department,
            subject="storage failure",
        )
        attachment = TicketAttachment.objects.create(
            ticket=ticket,
            file=SimpleUploadedFile("failure.txt", b"payload"),
            original_filename="failure.txt",
        )

        with patch("tickets.signals.TicketAttachment.file.field.storage.delete", side_effect=OSError("storage down")):
            with self.assertRaises(RuntimeError):
                attachment.delete()

        self.assertTrue(TicketAttachment.objects.filter(pk=attachment.pk).exists())
        self.assertTrue(Ticket.objects.filter(pk=ticket.pk).exists())
