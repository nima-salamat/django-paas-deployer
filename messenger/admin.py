from django.contrib import admin
from .models import (
    Contact, Block, Conversation, ConversationParticipant, Message,
    MessageReaction, MessageAttachment, GroupInviteLink,
    ProfilePhotoPrivacy, PinnedMessage,
)

admin.site.register(Contact)
admin.site.register(Block)
admin.site.register(Conversation)
admin.site.register(ConversationParticipant)
admin.site.register(Message)
admin.site.register(MessageReaction)
admin.site.register(MessageAttachment)
admin.site.register(GroupInviteLink)
admin.site.register(ProfilePhotoPrivacy)
admin.site.register(PinnedMessage)
