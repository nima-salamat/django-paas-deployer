from django.urls import path
from . import apis
urlpatterns = [
    path("templates/", apis.EmailTemplateListCreateAPIView.as_view()),
    path("templates/<int:pk>/", apis.EmailTemplateDetailAPIView.as_view()),
    path("templates/preview/", apis.EmailTemplatePreviewAPIView.as_view()),
    path("send/", apis.EmailSendAPIView.as_view()),
    path("logs/", apis.EmailLogListAPIView.as_view()),
    path("logs/<int:pk>/", apis.EmailLogDetailAPIView.as_view()),
]
