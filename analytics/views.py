# analytics/views.py
from django.db.models import Count
from rest_framework import viewsets, filters
from ingest.models import Dataset, DatasetRow
from .serializers import DatasetSerializer, DatasetRowSerializer
from django_filters.rest_framework import DjangoFilterBackend
from django.db.models.fields.json import KeyTextTransform

class DatasetViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = DatasetSerializer
    def get_queryset(self):
        qs = Dataset.objects.all().annotate(n=Count('rows'))  # <-- FIX
        if self.request.query_params.get("only_nonempty"):
            qs = qs.filter(n__gt=0)
        return qs.order_by("id")

class DatasetRowViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = DatasetRowSerializer
    filter_backends = [DjangoFilterBackend, filters.OrderingFilter]
    ordering = ["-id"]
    def get_queryset(self):
        ds_id = self.kwargs["dataset_id"]
        qs = DatasetRow.objects.filter(dataset_id=ds_id)
        q = self.request.query_params.get("q")
        if q and ":" in q:
            k, v = q.split(":", 1)
            qs = qs.annotate(_v=KeyTextTransform(k, "data")).filter(_v=v)  # <-- FIX
        return qs
