from rest_framework.routers import DefaultRouter
from .apis import ContainerViewSet, PrivateNetworkViewSet, VolumeViewSet

router = DefaultRouter()
router.register(r'service', ContainerViewSet, basename='service')
router.register(r'networks', PrivateNetworkViewSet, basename='private-network')
router.register(r'volume', VolumeViewSet, basename='volume')

urlpatterns = router.urls
