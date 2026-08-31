from django.urls import path
from .apis import (
    DeployViewSet,
    deploy_logs_apiview,
    deploy_name_is_available,
    set_deploy_apiview,
    unset_deploy_apiview,
    generate_db_credentials_apiview,
    inspect_deploy_zip_apiview,
    deploy_config_contract_apiview,
)

urlpatterns = [
    path('', DeployViewSet.as_view({'get': 'list', 'post': 'create'}), name='deploy-list'),
    path('<uuid:pk>/start/', DeployViewSet.as_view({'post': 'start'}), name='deploy-start'),
    path('<uuid:pk>/cancel/', DeployViewSet.as_view({'post': 'cancel'}), name='deploy-cancel'),
    path('<uuid:pk>/redeploy/', DeployViewSet.as_view({'post': 'redeploy'}), name='deploy-redeploy'),
    path('<uuid:pk>/rebuild/', DeployViewSet.as_view({'post': 'rebuild'}), name='deploy-rebuild'),
    path('<uuid:pk>/rollback/', DeployViewSet.as_view({'post': 'rollback'}), name='deploy-rollback'),
    path('<uuid:pk>/update_db_config/', DeployViewSet.as_view({'patch': 'update_db_config'}), name='deploy-update-db-config'),
    path('<uuid:pk>/reveal_db_credentials/', DeployViewSet.as_view({'get': 'reveal_db_credentials'}), name='deploy-reveal-db-credentials'),
    path('<uuid:pk>/logs/', deploy_logs_apiview, name='deploy_logs'),
    path('<uuid:pk>/download/', DeployViewSet.as_view({'get': 'download'}), name='deploy-download'),
    path('<uuid:pk>/', DeployViewSet.as_view({'get': 'retrieve', 'put': 'update', 'delete': 'destroy'}), name='deploy-detail'),
    path('name_is_available/', deploy_name_is_available, name='deploy_name_is_available'),
    path('set_deploy/', set_deploy_apiview, name='set_deploy'),
    path('unset_deploy/', unset_deploy_apiview, name='unset_deploy'),
    path('generate_db_credentials/', generate_db_credentials_apiview, name='deploy-generate-db-credentials'),
    path('inspect_zip/', inspect_deploy_zip_apiview, name='deploy-inspect-zip'),
    path('config_contract/', deploy_config_contract_apiview, name='deploy-config-contract'),
]
