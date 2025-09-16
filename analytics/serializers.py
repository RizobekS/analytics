from rest_framework import serializers

from .models import ChartConfig, Dashboard
from ingest.models import Dataset, DatasetRow

class DatasetSerializer(serializers.ModelSerializer):
    class Meta:
        model = Dataset
        fields = ["id", "name", "sheet_id", "inferred_schema", "meta"]

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
