from django.contrib import admin

from .models import AuditLog


@admin.register(AuditLog)
class AuditLogAdmin(admin.ModelAdmin):
    list_display = ("created_at", "farm", "actor", "action", "entity_type", "entity_id")
    list_filter = ("action",)
