from django.contrib import admin
from django.utils import timezone

from .models import AuthCode


@admin.register(AuthCode)
class AuthCodeAdmin(admin.ModelAdmin):
    list_display = (
        "user",
        "code",
        "created_at",
        "is_expired_display",
    )

    list_filter = (
        "created_at",
    )

    search_fields = (
        "user__username",
        "user__email",
        "code",
    )

    readonly_fields = (
        "created_at",
        "is_expired_display",
    )

    ordering = (
        "-created_at",
    )

    @admin.display(
        boolean=True,
        description="Expired",
    )
    def is_expired_display(self, obj):
        return obj.is_expired()