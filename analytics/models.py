from django.db import models
from django.conf import settings
from django.utils.text import slugify


class Dashboard(models.Model):
    title = models.CharField(max_length=200)
    owner = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    shared = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

class ChartConfig(models.Model):
    dashboard = models.ForeignKey(Dashboard, on_delete=models.CASCADE, related_name="charts")
    title = models.CharField(max_length=200)
    dataset = models.ForeignKey('ingest.Dataset', on_delete=models.PROTECT)

    # запрос агрегации
    group_by = models.CharField(max_length=100, help_text="имя поля в JSONB (например, region или date)")
    metric = models.CharField(max_length=50, help_text="sum:amount, avg:score и т.п.")
    # массив серий, если задан — metric выше игнорируем при построении
    series = models.JSONField(default=list, blank=True)
    filters = models.JSONField(default=dict, blank=True)


    # ECharts опции
    options = models.JSONField(default=dict, blank=True)
    order = models.IntegerField(default=0)

    slug = models.SlugField(max_length=200, unique=True, blank=True)
    published = models.BooleanField(default=False)

    # период и поле даты для AggregateView
    date_field = models.CharField(max_length=100, blank=True, default="")
    date_from = models.DateField(null=True, blank=True)
    date_to = models.DateField(null=True, blank=True)

    def save(self, *args, **kwargs):
        if not self.slug:
            base = f"{self.dashboard_id}-{self.title}"
            self.slug = slugify(base)[:200]
        super().save(*args, **kwargs)

    class Meta:
        indexes = [
            models.Index(fields=["dashboard", "order"]),
            models.Index(fields=["dataset", "published"]),
        ]
