# analytics/views.py
from django.db.models import CharField
from django.db.models.functions import Cast
from django.db.models import Count
from rest_framework import viewsets, filters, permissions
from ingest.models import Dataset, DatasetRow
from .serializers import DatasetSerializer, DatasetRowSerializer
from django_filters.rest_framework import DjangoFilterBackend
from django.db.models.fields.json import KeyTextTransform


class DatasetViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = DatasetSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        qs = Dataset.objects.all().annotate(n=Count('rows'))  # <-- FIX
        if self.request.query_params.get("only_nonempty"):
            qs = qs.filter(n__gt=0)
        return (qs
                .select_related('sheet__workbook')
                .order_by('id')
                )


class DatasetRowViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = DatasetRowSerializer
    filter_backends = [DjangoFilterBackend, filters.OrderingFilter]
    ordering = ["-id"]

    def get_queryset(self):
        ds_id = self.kwargs["dataset_id"]
        qs = DatasetRow.objects.filter(dataset_id=ds_id)

        # --- 1) Фильтр вида ?q=field:value — делаем НЕчувствительным к регистру (iexact)
        qparam = self.request.query_params.get("q")
        if qparam and ":" in qparam:
            k, v = qparam.split(":", 1)
            # безопасно извлекаем текст из JSONB по ключу k и приводим к CharField
            qs = qs.annotate(_qv=Cast(KeyTextTransform(k, "data"), output_field=CharField()))
            qs = qs.filter(_qv__iexact=v.strip())  # 'Р' == 'р', 'a' == 'A'

        # --- 2) Общий поиск по всем значениям JSON: ?search=... (подстрока, ILIKE)
        search = (self.request.query_params.get("search") or "").strip()
        if search:
            like = f"%{search}%"
            # jsonb_each_text пробегается по всем парам (k,v); берём совпадение по подстроке без учёта регистра
            qs = qs.extra(
                where=["EXISTS (SELECT 1 FROM jsonb_each_text(data) AS t(k,v) WHERE v ILIKE %s)"],
                params=[like],
            )

        # tab=... игнорируем (это тот же dataset)
        return qs
