from pathlib import Path
from tempfile import TemporaryDirectory

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings

from messenger.models import (
    Contact,
    Conversation,
    ConversationParticipant,
    Message,
    MessageAttachment,
    MessageReaction,
)
from users.models import User


class MessengerUserDeletionTests(TestCase):
    def test_group_owner_is_transferred_and_user_membership_data_is_removed(self):
        user = User.objects.create_user(username="messenger-delete", email="messenger-delete@example.invalid")
        other = User.objects.create_user(username="messenger-keep", email="messenger-keep@example.invalid")
        contact = Contact.objects.create(owner=user, contact=other)

        group = Conversation.objects.create(
            type=Conversation.Type.GROUP,
            title="Owned group",
            created_by=user,
        )
        owner = ConversationParticipant.objects.create(
            conversation=group,
            user=user,
            role=ConversationParticipant.Role.OWNER,
            can_add_members=True,
            can_pin_messages=True,
            can_change_info=True,
        )
        member = ConversationParticipant.objects.create(
            conversation=group,
            user=other,
            role=ConversationParticipant.Role.MEMBER,
        )
        message = Message.objects.create(conversation=group, sender=user, body="history")
        reaction = MessageReaction.objects.create(message=message, user=user, emoji=":thumbsup:")

        user.delete()

        self.assertFalse(Contact.objects.filter(pk=contact.pk).exists())
        self.assertFalse(ConversationParticipant.objects.filter(pk=owner.pk).exists())
        self.assertFalse(MessageReaction.objects.filter(pk=reaction.pk).exists())

        member.refresh_from_db()
        self.assertEqual(member.role, ConversationParticipant.Role.OWNER)
        message.refresh_from_db()
        self.assertIsNone(message.sender_id)
        self.assertTrue(Conversation.objects.filter(pk=group.pk).exists())

    def test_private_dm_is_deleted_with_its_media_when_a_participant_account_is_deleted(self):
        user = User.objects.create_user(username="dm-delete", email="dm-delete@example.invalid")
        other = User.objects.create_user(username="dm-keep", email="dm-keep@example.invalid")
        dm = Conversation.objects.create(type=Conversation.Type.PRIVATE, created_by=user)
        ConversationParticipant.objects.create(conversation=dm, user=user)
        ConversationParticipant.objects.create(conversation=dm, user=other)
        message = Message.objects.create(conversation=dm, sender=user, body="private")
        with TemporaryDirectory() as media_root, override_settings(MEDIA_ROOT=media_root):
            attachment = MessageAttachment.objects.create(
                conversation=dm,
                message=message,
                uploaded_by=user,
                file=SimpleUploadedFile("private.txt", b"private-media"),
                original_filename="private.txt",
            )
            path = Path(attachment.file.path)
            self.assertTrue(path.exists())

            user.delete()

            self.assertFalse(path.exists())

        self.assertFalse(Conversation.objects.filter(pk=dm.pk).exists())

    def test_group_deletion_cleans_avatar_and_group_service_share(self):
        from core.global_settings.config import NameChoices, PlanTypeChoices, StorageTypeChoices
        from plans.models import Plan
        from services.models import Service, ServiceShare

        user = User.objects.create_user(
            username="messenger-last-member",
            email="messenger-last-member@example.invalid",
        )
        service_owner = User.objects.create_user(
            username="messenger-service-owner",
            email="messenger-service-owner@example.invalid",
        )
        plan = Plan.objects.create(
            name=NameChoices.BRONZE,
            platform="docker",
            plan_type=PlanTypeChoices.APP,
            max_cpu=1,
            max_ram=512,
            max_storage=10,
            price_per_hour=0,
            storage_type=StorageTypeChoices.SSD,
        )
        service = Service.objects.create(
            name="shared-group-delete",
            user=service_owner,
            plan=plan,
        )

        with TemporaryDirectory() as media_root, override_settings(MEDIA_ROOT=media_root):
            group = Conversation.objects.create(
                type=Conversation.Type.GROUP,
                title="Disposable group",
                created_by=user,
                avatar=SimpleUploadedFile(
                    "group-avatar.png",
                    b"not-a-real-image-but-no-model-validator-runs-here",
                    content_type="image/png",
                ),
            )
            avatar_path = Path(group.avatar.path)
            ConversationParticipant.objects.create(
                conversation=group,
                user=user,
                role=ConversationParticipant.Role.OWNER,
            )
            share = ServiceShare.objects.create(
                service=service,
                group=group,
                shared_by=service_owner,
                rules={"can_view": True},
            )

            user.delete()

            self.assertFalse(Path(avatar_path).exists())
            self.assertFalse(Conversation.objects.filter(pk=group.pk).exists())
            self.assertFalse(ServiceShare.objects.filter(pk=share.pk).exists())
            self.assertTrue(Service.objects.filter(pk=service.pk).exists())
