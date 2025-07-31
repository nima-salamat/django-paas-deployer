from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from users.models import User, Profile, Rule
from django.contrib.auth.models import Group

@admin.site.unregister(Group)

@admin.register(User)
class UserAdmin(BaseUserAdmin):
    model = User
    list_display = ("id", "username", "email", "phone_number", "is_superuser", "is_active")
    fieldsets = (
        (None, {"fields": ("username", "email", "phone_number", "password")}),
        ("Permissions", {"fields": ("is_active", "is_staff", "is_superuser", "email_verified", "phone_number_verified")}),
        ("Important dates", {"fields": ("last_login", "date_joined","birthdate")}),
        ("Profile infor", {"fields": ("theme", "color")})
    )
    list_display_links = ["id", "username"]
    add_fieldsets = (
        (None, {
            "classes": ("wide",),
            "fields": ("username", "email", "phone_number", "password1", "password2", "is_staff", "is_superuser")}
        ),
    )
    search_fields = ("username", "email", "phone_number")
    ordering = ("id",)
    list_filter = []
    filter_horizontal = []
    


@admin.register(Profile)
class ProfileAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "order",
        "user",
        "image",
        "created_at",
    )
    list_display_links = ("id", "user")

    search_fields = ["user", "id", "order"]
    list_filter = ["created_at"]
    ordering = ["-created_at"]
    list_per_page = 20

    readonly_fields = ["created_at", "id"]
    



@admin.register(Rule)
class RuleAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "user",
        "rules",
        "updated_at",
        "created_at",
        
    )
    list_display_links = ("id", "user")

    search_fields = ["user", "id", "rules"]
    list_filter = ["created_at"]
    ordering = ["-created_at"]
    list_per_page = 20
    
    readonly_fields = ["created_at", "id"]
    
