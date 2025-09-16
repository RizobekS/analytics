from django.contrib import admin

from analytics.models import Dashboard, ChartConfig


@admin.register(Dashboard)
class DashboardAdmin(admin.ModelAdmin):
    list_display = ("title", "owner", "shared", "created_at")


@admin.register(ChartConfig)
class ChartConfigAdmin(admin.ModelAdmin):
    list_display = ("dashboard__title", "title", "dataset", "published")
