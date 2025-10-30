# egovuz_provider/admin.py
from django.contrib import admin
from .models import UserProfile

@admin.register(UserProfile)
class UserProfileAdmin(admin.ModelAdmin):
    list_display = ("user", "egov_uid", "pin", "full_name", "last_sync")
    search_fields = ("user__username", "user__email", "egov_uid", "pin", "full_name")
    list_filter = ("last_sync",)
