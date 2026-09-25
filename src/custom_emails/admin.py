from django.contrib import admin
from django.utils.html import format_html
from .models import EmailTemplate, EmailLog

@admin.register(EmailTemplate)
class EmailTemplateAdmin(admin.ModelAdmin):
    list_display = ("name","subject","is_active","created_at")
    list_filter = ("is_active",)
    search_fields = ("name","subject")
    readonly_fields = ("created_at","updated_at")

@admin.register(EmailLog)
class EmailLogAdmin(admin.ModelAdmin):
    list_display = ("id","recipient_email","subject","status","is_test","created_at","sent_at")
    list_filter = ("status","is_test")
    search_fields = ("recipient_email","subject")
    readonly_fields = ("recipient","recipient_email","template","subject","body_preview","status","error_message","sent_by","is_test","created_at","sent_at","failed_at","celery_task_id")
