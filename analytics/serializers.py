from rest_framework import serializers

from .models import ChartConfig, Dashboard
from ingest.models import Dataset, DatasetRow

class DatasetSerializer(serializers.ModelSerializer):
    fullname = serializers.CharField(source='sheet.workbook.filename', read_only=True)
    workbook_id = serializers.IntegerField(source='sheet.workbook_id', read_only=True)
    sheet_name = serializers.CharField(source='sheet.name', read_only=True)
    sheet_index = serializers.IntegerField(source='sheet.index', read_only=True)
    class Meta:
        model = Dataset
        fields = [
            "id", "name", "sheet_id", "inferred_schema", "meta",
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
