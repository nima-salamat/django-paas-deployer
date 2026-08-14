from django.urls import path
from . import apis

urlpatterns = [
    path("users/search/", apis.UserSearchAPIView.as_view()),
    path("contacts/", apis.ContactListCreateAPIView.as_view()),
    path("contacts/<int:user_id>/", apis.ContactDeleteAPIView.as_view()),
    path("blocks/", apis.BlockListCreateAPIView.as_view()),
    path("blocks/<int:user_id>/unblock/", apis.UnblockAPIView.as_view()),
    path("conversations/", apis.ConversationListCreateAPIView.as_view()),
    path("conversations/<int:pk>/", apis.ConversationDetailAPIView.as_view()),
    path("conversations/<int:pk>/messages/", apis.MessageListCreateAPIView.as_view()),
    path("conversations/<int:pk>/read/", apis.MarkReadAPIView.as_view()),
    path("conversations/<int:pk>/pin/", apis.ConversationPinAPIView.as_view()),
    path("conversations/<int:pk>/invite-links/", apis.InviteLinkCreateAPIView.as_view()),
    path("conversations/<int:pk>/invite-links/<int:link_id>/revoke/", apis.InviteLinkRevokeAPIView.as_view()),
    path("groups/search/", apis.PublicGroupSearchAPIView.as_view()),
    path("groups/<int:pk>/join/", apis.PublicGroupJoinAPIView.as_view()),
    path("join/<str:code>/", apis.JoinByInviteAPIView.as_view()),
    path("messages/<int:pk>/forward/", apis.MessageForwardAPIView.as_view()),
    path("messages/<int:pk>/react/", apis.MessageReactAPIView.as_view()),
    path("messages/<int:pk>/edit/", apis.MessageEditAPIView.as_view()),
    path("messages/<int:pk>/pin/", apis.MessagePinAPIView.as_view()),
    path("messages/<int:pk>/readers/", apis.MessageReadersAPIView.as_view()),
    path("messages/<int:pk>/", apis.MessageDeleteAPIView.as_view()),
    path("conversations/<int:pk>/pinned-messages/", apis.ConversationPinnedMessagesAPIView.as_view()),
    path("conversations/<int:pk>/leave/", apis.LeaveConversationAPIView.as_view()),
    path("conversations/<int:pk>/members/", apis.AddMembersAPIView.as_view()),
    # Group management — remove member, change role, transfer ownership
    path("conversations/<int:pk>/members/<int:user_id>/", apis.RemoveMemberAPIView.as_view()),
    path("conversations/<int:pk>/members/<int:user_id>/role/", apis.MemberRoleAPIView.as_view()),
    path("conversations/<int:pk>/transfer-ownership/", apis.TransferOwnershipAPIView.as_view()),
    path("conversations/<int:pk>/delete/", apis.DeleteConversationAPIView.as_view()),
    path("attachments/<int:pk>/download/", apis.AttachmentDownloadAPIView.as_view()),
    path("me/photos/", apis.MyProfilePhotosAPIView.as_view()),
    path("me/photo-privacy/", apis.ProfilePhotoPrivacyAPIView.as_view()),
    path("users/<int:user_id>/profile/", apis.UserProfileAPIView.as_view()),
    path("users/by-username/", apis.UserByUsernameAPIView.as_view()),
    path("conversations/<int:pk>/cleanup/", apis.ConversationCleanupAPIView.as_view()),
    path("conversations/<int:pk>/media/", apis.ConversationMediaAPIView.as_view()),
    # User bio (Telegram-style 'about')
    path("me/bio/", apis.UserBioAPIView.as_view()),
    # Group avatar upload/clear
    path("conversations/<int:pk>/avatar/", apis.GroupAvatarAPIView.as_view()),
    # Join requests (Telegram-style — public groups that require admin approval)
    path("conversations/<int:pk>/join-requests/", apis.JoinRequestListAPIView.as_view()),
    path("conversations/<int:pk>/join-requests/<int:req_id>/action/", apis.JoinRequestActionAPIView.as_view()),
    path("me/join-requests/", apis.MyJoinRequestsAPIView.as_view()),
    path("join-requests/<int:req_id>/", apis.JoinRequestCancelAPIView.as_view()),
    # Profile update broadcast (notifies all conversations of avatar/bio change)
    path("me/profile-broadcast/", apis.ProfileUpdateBroadcastAPIView.as_view()),
    # Jitsi video/audio calls
    path("conversations/<int:pk>/call/", apis.ConversationCallStartAPIView.as_view()),
    path("conversations/<int:pk>/call/join/", apis.ConversationCallJoinAPIView.as_view()),
    path("conversations/<int:pk>/call/active/", apis.ConversationCallActiveAPIView.as_view()),
    path("conversations/<int:pk>/call/end/", apis.ConversationCallEndAPIView.as_view()),
]
