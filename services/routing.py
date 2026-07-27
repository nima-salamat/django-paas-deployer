from django.urls import re_path

from .consumers import ServiceLogsConsumer

websocket_urlpatterns = [
    re_path(r"ws/services/logs/(?P<service_id>[0-9a-fA-F-]+)/$", ServiceLogsConsumer.as_asgi()),
]
