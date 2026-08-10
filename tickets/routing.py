from django.urls import re_path

from .consumers import TicketEventsConsumer, TicketNotifyConsumer

websocket_urlpatterns = [
    re_path(r"ws/tickets/$", TicketEventsConsumer.as_asgi()),
    re_path(r"ws/tickets/notify/$", TicketNotifyConsumer.as_asgi()),
]
