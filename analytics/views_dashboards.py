# analytics/views_dashboards.py
import copy

from django.contrib.auth.mixins import LoginRequiredMixin
from django.db.models import Q
from django.views.generic import TemplateView
from rest_framework import viewsets, permissions
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.authentication import SessionAuthentication, BasicAuthentication

from web_project import TemplateLayout
from ingest.models import DatasetRow
from .models import Dashboard, ChartConfig
from .serializers import DashboardSerializer, ChartConfigSerializer
from .views_aggregate import _aggregate_core  # как мы выделяли ранее

class IsOwnerOrShared(permissions.BasePermission):
    def has_object_permission(self, request, view, obj):
        if isinstance(obj, Dashboard):
            return obj.shared or obj.owner == request.user or request.user.is_superuser
        return True

class DashboardViewSet(viewsets.ModelViewSet):
    """
    /api/dashboards/ — лист/создание/редактирование дашбордов.
    """
    authentication_classes = [SessionAuthentication, BasicAuthentication]
    permission_classes = [permissions.IsAuthenticated, IsOwnerOrShared]
    serializer_class = DashboardSerializer

    def get_queryset(self):
        u = self.request.user
        return Dashboard.objects.filter(Q(shared=True) | Q(owner=u) | Q(owner__isnull=True)).order_by("id")

    def perform_create(self, serializer):
        serializer.save(owner=self.request.user)

class ChartConfigViewSet(viewsets.ModelViewSet):
    """
    /api/charts/ — лист/создание/редактирование чартов.
    GET /api/charts/{id}/data/ — агрегированные данные для отрисовки.
    """
    authentication_classes = [SessionAuthentication, BasicAuthentication]
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = ChartConfigSerializer

    def get_queryset(self):
        qs = ChartConfig.objects.all()
        ds = self.request.query_params.get("dataset")
        if ds:
            qs = qs.filter(dataset_id=ds)
        # если у тебя уже есть поле published=True — можно дать фильтр ?published=1
        pub = self.request.query_params.get("published")
        if pub in ("1", "true", "yes"):
            if hasattr(ChartConfig, "published"):
                qs = qs.filter(published=True)
            else:
                # без поля published показываем те, что лежат в расшаренных дашбордах
                qs = qs.filter(dashboard__shared=True)
        return qs.order_by("order", "id")

    @action(detail=True, methods=["get"], url_path="data")
    def data(self, request, pk=None):
        chart = self.get_object()
        qs = DatasetRow.objects.filter(dataset_id=chart.dataset_id)

        # валидные ключи (семпл)
        sample = qs.values_list("data", flat=True)[:1000]
        valid_keys = set()
        for d in sample:
            if isinstance(d, dict):
                valid_keys.update(d.keys())
        valid_keys = list(valid_keys)

        group_by = chart.group_by or None

        # --- соберём список серий ---
        def series_list_from_chart(ch):
            if ch.series:
                out = []
                for it in ch.series:
                    m = (it.get("metric") or "count").lower()
                    f = it.get("field") or ""
                    n = it.get("name") or (f or m)
                    out.append({"metric": m, "field": f, "name": n})
                return out
            # fallback: одиночная серия из ch.metric
            agg, _, fld = (ch.metric or "count:id").partition(":")
            return [{"metric": (agg or "count").lower(), "field": fld, "name": ch.title or f"{agg}:{fld}"}]

        series_cfg = series_list_from_chart(chart)

        # даты
        date_field = getattr(chart, "date_field", None) or None
        cf_from = getattr(chart, "date_from", None)
        cf_to = getattr(chart, "date_to", None)
        date_from = request.query_params.get("date_from") or (cf_from.isoformat() if cf_from else None)
        date_to = request.query_params.get("date_to") or (cf_to.isoformat() if cf_to else None)

        # filters из конфига + getlist() из URL (списки поддерживаем)
        filters = copy.deepcopy(chart.filters or {})
        excludes = {}
        for k, vals in request.query_params.lists():
            if k.startswith("filters[") and k.endswith("]"):
                key = k[len("filters["):-1]
                if key in filters:
                    if isinstance(filters[key], list):
                        filters[key].extend(vals)
                    else:
                        filters[key] = [filters[key]] + vals
                else:
                    filters[key] = vals
            if k.startswith("exclude[") and k.endswith("]"):
                key = k[len("exclude["):-1]
                excludes[key] = vals if len(vals) > 1 else (vals[0] if vals else None)

        # --- получим ось X (порядок) ---
        # если filters по group_by содержит список — используем его как порядок
        order_list = None
        if group_by and isinstance(filters.get(group_by), list) and filters[group_by]:
            order_list = [str(x) for x in filters[group_by]]

        # вспомогалка для одной серии
        def run_one(metric_name, field_name):
            mstr = f"{metric_name}:{('id' if metric_name == 'count' else (field_name or ''))}"
            payload = _aggregate_core(
                qs=qs, valid_keys=valid_keys,
                group_by=group_by, metric=mstr,
                date_field=date_field, date_from=date_from, date_to=date_to,
                filters=filters, excludes=excludes
            )
            rows = payload.get("data") or []
            x = [r["key"] for r in rows]
            y = [float(r["value"] or 0) for r in rows]
            return x, y

        # запускаем первую серию, чтобы определить X при отсутствии order_list
        x0, y0 = run_one(series_cfg[0]["metric"], series_cfg[0]["field"])
        X = order_list if order_list else x0

        # соберём все серии, выравнивая по X
        out_series = []

        # первая уже есть
        def to_map(x, y):
            return {str(k): v for k, v in zip(x, y)}

        maps = [to_map(x0, y0)]

        for cfg in series_cfg[1:]:
            xi, yi = run_one(cfg["metric"], cfg["field"])
            maps.append(to_map(xi, yi))

        # склеиваем в нужном порядке
        for idx, cfg in enumerate(series_cfg):
            out_series.append({
                "name": cfg["name"],
                "data": [maps[idx].get(str(k), 0) for k in X]
            })

        # для обратной совместимости положим ещё и "data" как первую серию
        legacy_data = [{"key": str(k), "value": out_series[0]["data"][i] if out_series else 0} for i, k in enumerate(X)]

        return Response({"x": X, "series": out_series, "data": legacy_data})

class DashboardView(LoginRequiredMixin, TemplateView):
    template_name = "analytics/dashboard.html"
    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        return TemplateLayout().init(ctx)


class MIITGrpDashboardView(LoginRequiredMixin, TemplateView):
    template_name = "analytics/miit_grp.html"
    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        return TemplateLayout().init(ctx)
