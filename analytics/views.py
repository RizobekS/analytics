from django.db.models import CharField, F, Window
from django.db.models.functions import Cast, RowNumber
from django.db.models import Count
from rest_framework import viewsets, filters, permissions
from django_filters.rest_framework import DjangoFilterBackend
from django.db.models.fields.json import KeyTextTransform

from ingest.models import Dataset, DatasetRow
from .serializers import DatasetSerializer, DatasetRowSerializer


class DatasetViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = DatasetSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        qs = Dataset.objects.all().annotate(n=Count('rows'))
        if self.request.query_params.get("only_nonempty"):
            qs = qs.filter(n__gt=0)
        return qs.select_related('sheet__workbook').order_by('id')


class DatasetRowViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = DatasetRowSerializer
    filter_backends = [DjangoFilterBackend, filters.OrderingFilter]
    ordering = ["id"]

    def get_queryset(self):
        ds_id = self.kwargs["dataset_id"]

        # --- 0) дефолт start_row: берём из meta.start_row или =1
        meta = (Dataset.objects.filter(id=ds_id)
                .values_list("meta", flat=True).first()) or {}
        default_start_row = 1
        try:
            if isinstance(meta, dict) and "start_row" in meta:
                default_start_row = max(1, int(meta.get("start_row") or 1))
        except Exception:
            default_start_row = 1

        start_row_param = self.request.query_params.get("start_row")
        try:
            start_row = max(1, int(start_row_param)) if start_row_param else default_start_row
        except ValueError:
            start_row = default_start_row

        # --- 1) вычисляем «пороговый id» N-й строки (по id ASC) БЕЗ фильтров
        base_qs = DatasetRow.objects.filter(dataset_id=ds_id).order_by("id")
        if start_row > 1:
            # получаем id строки с порядковым номером start_row
            try:
                threshold_id = base_qs.values_list("id", flat=True)[start_row - 1]
            except IndexError:
                # если строк меньше, чем start_row — вернём пусто
                return DatasetRow.objects.none()
            qs = base_qs.filter(id__gte=threshold_id)
        else:
            qs = base_qs

        # --- 2) q=field:value (без учёта регистра)
        qparam = self.request.query_params.get("q")
        if qparam and ":" in qparam:
            k, v = qparam.split(":", 1)
            qs = qs.annotate(_qv=Cast(KeyTextTransform(k, "data"), output_field=CharField()))
            qs = qs.filter(_qv__iexact=v.strip())

        # --- 3) search=... : ищем по ключам И значениям (подстрока, без регистра)
        search = (self.request.query_params.get("search") or "").strip()
        if search:
            like = f"%{search}%"
            qs = qs.extra(
                where=[
                    "EXISTS (SELECT 1 FROM jsonb_each_text(data) AS t(k,v) WHERE k ILIKE %s OR v ILIKE %s)"
                ],
                params=[like, like],
            )

        return qs
