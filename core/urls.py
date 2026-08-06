from django.urls import path
from .apis import DeploymentDownloadAPIView  

urlpatterns = [
    path(
        "<uuid:pk>/download/",
        DeploymentDownloadAPIView.as_view(),
        name="deploy-download",
    ),
]