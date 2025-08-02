from rest_framework import serializers
from .models import Plan

class PlanSerializer(serializers.ModelSerializer):
    class Meta:
        model = Plan
        fields = "__all__"
        read_only_fields = ["id", "created_at", "updated_at"]


class UnauthorizedPlanSerializer(serializers.ModelSerializer):
    class Meta:
        model = Plan
        fields = [
            "name", "platform", "max_cpu", "max_ram",
            "max_storage","storage_type", "plan_type",
            "price_per_hour", "price_per_day","price_per_hour"
        ]
