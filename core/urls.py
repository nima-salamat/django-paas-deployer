from django.urls import path
from .apis import DeploymentDownloadAPIView, ProtectedMediaView

urlpatterns = [
    path(
        "<uuid:pk>/download/",
        DeploymentDownloadAPIView.as_view(),
        name="deploy-download",
    ),
    # Protected media — JWT-authenticated file serving.
    # Accepts Authorization header or ?token= query (so <img src="..."> works).
    #
    # /media/messenger/<path>  → group avatars + message attachments
    # /media/images/<path>     → user profile photos (users.Profile.image)
    # /media/tickets/<path>    → ticket attachments (TicketAttachment.file)
    #
    # All of these MUST go through Django (not nginx) so the JWT auth policy
    # is actually enforced. Serving them via nginx `alias` would bypass auth.
    path(
        "messenger/<path:path>",
        ProtectedMediaView.as_view(),
        name="protected-media",
    ),
    path(
        "images/<path:path>",
        ProtectedMediaView.as_view(),
        name="protected-media-images",
    ),
    path(
        "tickets/<path:path>",
        ProtectedMediaView.as_view(),
        name="protected-media-tickets",
    ),
]
