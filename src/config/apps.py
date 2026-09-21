from __future__ import annotations

from wagtail.users.apps import WagtailUsersAppConfig


class CustomWagtailUsersAppConfig(WagtailUsersAppConfig):
    """Wagtail users app configured with the project's custom user forms."""

    user_viewset = "cms.viewsets.UserViewSet"
