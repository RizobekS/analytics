# analytics/views_datasets.py
from django.contrib.auth.mixins import LoginRequiredMixin
from django.db.models import Count
from django.views.generic import TemplateView
from rest_framework.views import APIView
from rest_framework.response import Response
from ingest.models import Dataset
from web_project import TemplateLayout


class DatasetList(APIView):
    def get(self, request):
        qs = Dataset.objects.all().annotate(rows_count=Count('datasetrow'))
        if request.query_params.get('only_nonempty') in ('1','true','yes'):
            qs = qs.filter(rows_count__gt=0)
        data = [
            {
                "id": d.id,
                "name": d.name,
                "period_date": d.period_date.isoformat() if d.period_date else None,
                "rows_count": d.rows_count,
            }
            for d in qs.order_by('id')
        ]
        return Response(data)


class DatasetTableView(LoginRequiredMixin, TemplateView):
    """
    Страница /api/table/<dataset_id>/ — выводит опубликованные графики (ChartConfig)
    для конкретной таблицы. Данные для графиков подтягиваем на фронте через /api/charts/:id/data/.
    """
    template_name = "analytics/table.html"

    def get_context_data(self, dataset_id: int, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ds = Dataset.objects.filter(id=dataset_id).first()
        ctx["dataset"] = ds
        ctx["dataset_id"] = dataset_id
        return TemplateLayout().init(ctx)
