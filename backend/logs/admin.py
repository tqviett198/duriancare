from django.contrib import admin

from .models import FarmLog, FarmLogInput


class InputInline(admin.TabularInline):
    model = FarmLogInput
    extra = 0


@admin.register(FarmLog)
class FarmLogAdmin(admin.ModelAdmin):
    list_display = ("id", "plot", "activity_type", "activity_date", "status")
    list_filter = ("activity_type", "status")
    inlines = [InputInline]
