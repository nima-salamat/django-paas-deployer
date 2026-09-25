from django.urls import path
from .views import plan_list

urlpatterns = [
    path("plans/", plan_list, name="plan-list-html"),
]
