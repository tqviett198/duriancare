from django.contrib import admin

from .models import InputProduct, Variety


@admin.register(Variety)
class VarietyAdmin(admin.ModelAdmin):
    list_display = ("name", "is_active")


@admin.register(InputProduct)
class InputProductAdmin(admin.ModelAdmin):
    list_display = ("name", "kind", "phi_days", "registered_for_durian", "verified_at", "is_demo", "farm")
    list_filter = ("kind", "registered_for_durian", "is_demo")
    search_fields = ("name", "active_ingredient")
