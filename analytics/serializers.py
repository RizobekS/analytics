from rest_framework import serializers

from .models import ChartConfig, Dashboard
from ingest.models import Dataset, DatasetRow, HandleRegistry, Workbook
from .views_resolve import format_client_date


class DatasetSerializer(serializers.ModelSerializer):
    fullname = serializers.CharField(source='sheet.workbook.filename', read_only=True)
    workbook_id = serializers.IntegerField(source='sheet.workbook_id', read_only=True)
    sheet_name = serializers.CharField(source='sheet.name', read_only=True)
    handle = serializers.CharField(source='sheet.workbook.handle', read_only=True)
    period_date = serializers.DateField(source='sheet.workbook.period_date', read_only=True, format="%d.%m.%Y")
    sheet_index = serializers.IntegerField(source='sheet.index', read_only=True)
    class Meta:
        model = Dataset
        fields = [
            "id", "name", "sheet_id", "inferred_schema", "meta", "handle", "period_date", "status", "version",
            "fullname", "workbook_id","sheet_name", "sheet_index",
        ]

class DatasetRowSerializer(serializers.ModelSerializer):
    class Meta:
        model = DatasetRow
        fields = ["id", "data", "imported_at"]


class ChartConfigSerializer(serializers.ModelSerializer):
    class Meta:
        model = ChartConfig
        fields = "__all__"

class DashboardSerializer(serializers.ModelSerializer):
    charts = ChartConfigSerializer(many=True, read_only=True)
    class Meta:
        model = Dashboard
        fields = "__all__"


class HandleRegistrySerializer(serializers.ModelSerializer):
    # дополнительные, вычисляемые поля
    periods = serializers.SerializerMethodField()
    fullname = serializers.SerializerMethodField()

    class Meta:
        model = HandleRegistry
        fields = [
            "id",
            "handle",
            "title",
            "order_index",
            "group",
            "visible",
            "icon",
            "color",
            "style_json",
            # новые:
            "fullname",
            "periods",
        ]

    def get_fullname(self, obj):
        # читаемое имя таблицы для сайдбара
        qs = (Workbook.objects
              .filter(handle=obj.handle)
              .values_list("filename", flat=True)
              .order_by("-period_date", "-id"))
        return [f for f in qs if f]

    def get_periods(self, obj):
        # список всех периодов по handle, отсортированных по убыванию
        qs = (Workbook.objects
              .filter(handle=obj.handle)
              .values_list("period_date", flat=True)
              .order_by("-period_date", "-id"))
        # форматируем под фронт (DD.MM.YYYY), убираем None
        return [format_client_date(d) for d in qs if d]
