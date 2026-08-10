import os

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

from django.core.asgi import get_asgi_application

django_asgi_app = get_asgi_application()

from channels.auth import AuthMiddlewareStack
from channels.routing import ProtocolTypeRouter, URLRouter

import services.routing
import deployments.routing
import tickets.routing

combined_ws = (
    services.routing.websocket_urlpatterns +
    deployments.routing.websocket_urlpatterns +
    tickets.routing.websocket_urlpatterns
)

application = ProtocolTypeRouter({
    "http": django_asgi_app,
    "websocket": AuthMiddlewareStack(
        URLRouter(combined_ws)
    ),
})