from django.contrib import admin
from django.utils.html import format_html
from .models import Department, DepartmentMembership, Ticket, TicketMessage, TicketAttachment

class DepartmentMembershipInline(admin.TabularInline):
    model = DepartmentMembership
    extra = 0
    autocomplete_fields = ("user",)
    fields = ("user", "is_manager", "created_at")
    readonly_fields = ("created_at",)

@admin.register(Department)
class DepartmentAdmin(admin.ModelAdmin):
    list_display = ("name", "slug", "is_active", "order", "created_at")
    list_filter = ("is_active",)
    search_fields = ("name", "slug")
    prepopulated_fields = {"slug": ("name",)}
    inlines = [DepartmentMembershipInline]

class TicketMessageInline(admin.TabularInline):
    model = TicketMessage
    extra = 0
    readonly_fields = ("author", "is_staff_reply", "created_at")
    fields = ("author", "is_staff_reply", "body", "created_at")
    can_delete = False
    show_change_link = True

class TicketAttachmentInline(admin.TabularInline):
    model = TicketAttachment
    extra = 0
    readonly_fields = ("original_filename", "content_type", "size", "uploaded_by", "created_at")
    fields = ("original_filename", "content_type", "size", "uploaded_by", "created_at")

@admin.register(Ticket)
class TicketAdmin(admin.ModelAdmin):
    list_display = ("public_id", "subject", "user", "department", "service", "deploy", "status", "priority", "last_message_at", "created_at")
    list_filter = ("status", "priority", "department")
    search_fields = ("public_id", "subject", "user__username", "service__name")
    readonly_fields = ("public_id", "created_at", "updated_at", "closed_at", "last_message_at")
    autocomplete_fields = ("user", "assigned_to", "department")
    raw_id_fields = ("service", "deploy")
    inlines = [TicketMessageInline, TicketAttachmentInline]
    list_select_related = ("user", "department", "service", "deploy")
    fieldsets = (
        (None, {"fields": ("public_id", "subject", "user", "department")}),
        ("Related resources", {"fields": ("service", "deploy"), "classes": ("collapse",)}),
        ("Status", {"fields": ("status", "priority", "assigned_to")}),
        ("Timestamps", {"fields": ("created_at", "updated_at", "last_message_at", "closed_at")}),
    )

@admin.register(TicketMessage)
class TicketMessageAdmin(admin.ModelAdmin):
    list_display = ("id", "ticket", "author", "is_staff_reply", "created_at")
    list_filter = ("is_staff_reply",)
    search_fields = ("ticket__public_id", "body")
    autocomplete_fields = ("ticket", "author")

@admin.register(TicketAttachment)
class TicketAttachmentAdmin(admin.ModelAdmin):
    list_display = ("original_filename", "ticket", "size", "uploaded_by", "created_at")
    search_fields = ("original_filename", "ticket__public_id")

@admin.register(DepartmentMembership)
class DepartmentMembershipAdmin(admin.ModelAdmin):
    list_display = ("user", "department", "is_manager", "created_at")
    list_filter = ("is_manager", "department")
    autocomplete_fields = ("user", "department")
