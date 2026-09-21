from django.urls import re_path
from .consumers import DeploymentConsumer

websocket_urlpatterns = [
    re_path(r"ws/deployments/(?P<deploy_id>[0-9a-fA-F-]+)/$", DeploymentConsumer.as_asgi()),
]
