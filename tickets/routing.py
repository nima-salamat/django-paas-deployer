from django.urls import re_path
from .consumers import TicketEventsConsumer

websocket_urlpatterns = [
    re_path(r"ws/tickets/$", TicketEventsConsumer.as_asgi()),
]
