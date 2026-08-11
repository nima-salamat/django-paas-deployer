from django.urls import path
from .apis import DeploymentDownloadAPIView, ProtectedMediaView

urlpatterns = [
    path(
        "<uuid:pk>/download/",
        DeploymentDownloadAPIView.as_view(),
        name="deploy-download",
    ),
    # Protected media — JWT-authenticated file serving for /media/messenger/...
    # Accepts Authorization header or ?token= query (so <img src="..."> works).
    path(
        "messenger/<path:path>",
        ProtectedMediaView.as_view(),
        name="protected-media",
    ),
]
