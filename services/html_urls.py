from django.urls import path
from .views import services_list, service_detail

urlpatterns = [
    path('', services_list, name='services_list_html'),
    path('<uuid:pk>/', service_detail, name='service_detail_html'),
]
