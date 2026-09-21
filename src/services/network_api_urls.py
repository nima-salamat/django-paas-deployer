from rest_framework.routers import DefaultRouter
from services.apis import PrivateNetworkViewSet

router = DefaultRouter()
router.register(r"", PrivateNetworkViewSet, basename="network")

urlpatterns = router.urls
