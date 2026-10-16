from django.contrib import admin
from django.contrib.auth.admin import UserAdmin

from .models import User


@admin.register(User)
class DurianUserAdmin(UserAdmin):
    fieldsets = UserAdmin.fieldsets + (("Thông tin thêm", {"fields": ("phone", "full_name")}),)
    list_display = ("username", "phone", "full_name", "is_staff")
    search_fields = ("phone", "full_name")
