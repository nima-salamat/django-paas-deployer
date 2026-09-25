from django.urls import path
from . import consumers

websocket_urlpatterns = [
    path("ws/messenger/", consumers.MessengerConsumer.as_asgi()),
]
