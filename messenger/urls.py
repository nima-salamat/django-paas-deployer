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
    path("conversations/<int:pk>/invite-links/", apis.InviteLinkCreateAPIView.as_view()),
    path("conversations/<int:pk>/invite-links/<int:link_id>/revoke/", apis.InviteLinkRevokeAPIView.as_view()),
    path("groups/search/", apis.PublicGroupSearchAPIView.as_view()),
    path("join/<str:code>/", apis.JoinByInviteAPIView.as_view()),
    path("messages/<int:pk>/forward/", apis.MessageForwardAPIView.as_view()),
    path("messages/<int:pk>/react/", apis.MessageReactAPIView.as_view()),
    path("messages/<int:pk>/", apis.MessageDeleteAPIView.as_view()),
    path("attachments/<int:pk>/download/", apis.AttachmentDownloadAPIView.as_view()),
    path("me/photos/", apis.MyProfilePhotosAPIView.as_view()),
    path("me/photos/<int:photo_id>/", apis.ProfilePhotoDeleteAPIView.as_view()),
    path("me/photo-privacy/", apis.ProfilePhotoPrivacyAPIView.as_view()),
    path("users/<int:user_id>/profile/", apis.UserProfileAPIView.as_view()),
]
