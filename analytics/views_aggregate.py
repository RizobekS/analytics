# analytics/views_aggregate.py
from django.db.models.fields.json import KeyTextTransform
from django.utils.decorators import method_decorator
from django.views.decorators.cache import cache_page
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from django.db.models import Sum, Avg, Min, Max, Count, Value, CharField, DecimalField, Q, Case, When, F, TextField
from django.db.models.functions import Cast, Replace, Coalesce
from ingest.models import DatasetRow

NUM_FIELD = DecimalField(max_digits=24, decimal_places=6)

def resolve_key_case_insensitive(valid_keys, requested):
    if not requested:
        return None
    if requested in valid_keys:
        return requested
    lowmap = {k.lower(): k for k in valid_keys}
    return lowmap.get(str(requested).lower(), requested)

def _aggregate_core(
    qs,
    valid_keys,
    group_by: str | None,
    metric: str,
    date_field: str | None,
    date_from: str | None,
    date_to: str | None,
    filters: dict | None,
    excludes: dict | None,
):
    filters = filters or {}
    excludes = excludes or {}

    group_by = resolve_key_case_insensitive(valid_keys, group_by)
    date_field = resolve_key_case_insensitive(valid_keys, date_field)

    agg_name, _, metric_field = (metric or "count:id").partition(":")
    agg_name = (agg_name or "count").lower()
    metric_field = resolve_key_case_insensitive(valid_keys, metric_field)

    # --- include filters (поддержка списков и порядка) ---
    for k, v in filters.items():
        rk = resolve_key_case_insensitive(valid_keys, k)
        if not rk:
            continue
        qs = qs.annotate(_flt=KeyTextTransform(rk, "data"))
        if isinstance(v, (list, tuple)):
            qs = qs.filter(_flt__in=list(v))
        else:
            qs = qs.filter(_flt=v)

    # --- exclude filters (поддержка списков) ---
    for k, v in excludes.items():
        rk = resolve_key_case_insensitive(valid_keys, k)
        if not rk:
            continue
        qs = qs.annotate(_ex=KeyTextTransform(rk, "data"))
        if isinstance(v, (list, tuple)):
            qs = qs.exclude(_ex__in=list(v))
        else:
            qs = qs.exclude(_ex=v)

    # --- даты ---
    if date_field and (date_from or date_to):
        dt_text = KeyTextTransform(date_field, "data")
        qs = qs.annotate(_dtxt=dt_text)
        if date_from:
            qs = qs.filter(_dtxt__gte=date_from)
        if date_to:
            qs = qs.filter(_dtxt__lte=date_to)

    # --- безопасная конверсия чисел (проверяем regex на очищенной строке) ---
    def build_num_expr(values_qs, field_name):
        # ❗ raw: всегда TextField, NULL -> ''
        raw = Coalesce(
            Cast(KeyTextTransform(field_name, "data"), output_field=TextField()),
            Value("", output_field=TextField()),
            output_field=TextField(),
        )
        vq = values_qs.annotate(_raw=raw)

        # Все узлы Replace и литералы тоже как TextField
        _no_nbsp = Replace(
            F("_raw"),
            Value("\xa0", output_field=TextField()),
            Value("", output_field=TextField()),
            output_field=TextField(),
        )
        _no_sp = Replace(
            _no_nbsp,
            Value(" ", output_field=TextField()),
            Value("", output_field=TextField()),
            output_field=TextField(),
        )
        _dot = Replace(
            _no_sp,
            Value(",", output_field=TextField()),
            Value(".", output_field=TextField()),
            output_field=TextField(),
        )

        vq = vq.annotate(_san=_dot)

        cond = Q(_san__regex=r'^\s*-?\d+(?:\.\d+)?\s*$')
        num = Case(
            When(cond, then=Cast(F("_san"), output_field=NUM_FIELD)),
            default=Value(None),
            output_field=NUM_FIELD,
        )
        return vq, num

    data = []
    # если фильтр по group_by содержит список — запомним порядок
    order_list = None
    if group_by and isinstance(filters.get(group_by), (list, tuple)):
        order_list = [str(x) for x in filters[group_by]]

    if group_by:
        gb_text = KeyTextTransform(group_by, "data")
        qs = qs.annotate(
            _k=Coalesce(
                Cast(gb_text, output_field=TextField()),
                Value("", output_field=TextField()),
                output_field=TextField(),
            )
        )
        values = qs.values("_k")

        if agg_name in ("sum", "avg", "min", "max"):
            if not metric_field:
                raise ValueError("metric field required for non-count metrics")
            values, num_expr = build_num_expr(values, metric_field)
            agg_map = {"sum": Sum, "avg": Avg, "min": Min, "max": Max}
            rows = values.annotate(value=agg_map[agg_name](num_expr))
        else:
            rows = values.annotate(value=Count("id"))

        # rows -> map, затем собираем data по order_list если задан
        row_map = {r["_k"]: (r["value"] or 0) for r in rows}
        if order_list:
            for k in order_list:
                if k in row_map:
                    data.append({"key": k, "value": float(row_map[k] or 0)})
            # при желании можно добавить "хвост" (прочие ключи), но тебе нужен строгий порядок списка
        else:
            # если списка нет — просто сортируем по ключу
            for k in sorted(row_map.keys()):
                data.append({"key": k, "value": float(row_map[k] or 0)})

    else:
        if agg_name in ("sum", "avg", "min", "max"):
            if not metric_field:
                raise ValueError("metric field required for non-count metrics")
            values = qs.values()
            values, num_expr = build_num_expr(values, metric_field)
            agg_map = {"sum": Sum, "avg": Avg, "min": Min, "max": Max}
            val = values.aggregate(value=agg_map[agg_name](num_expr))["value"]
        else:
            val = qs.count()
        data = [{"key": "all", "value": float(val or 0)}]

    return {"data": data}


class AggregateView(APIView):
    permission_classes = [IsAuthenticated]

    @method_decorator(cache_page(60))
    def get(self, request):
        # 1) dataset_id
        ds_id = request.query_params.get("dataset_id")
        if not ds_id:
            return Response({"detail": "dataset_id is required"}, status=400)
        try:
            ds_id = int(ds_id)
        except ValueError:
            return Response({"detail": "dataset_id must be int"}, status=400)

        # 2) параметры
        group_by = request.query_params.get("group_by") or None
        metric = request.query_params.get("metric") or "count:id"
        date_field = request.query_params.get("date_field") or None
        date_from = request.query_params.get("date_from")
        date_to = request.query_params.get("date_to")

        filters, excludes = {}, {}
        for k, vals in request.query_params.lists():
            if k.startswith("filters[") and k.endswith("]"):
                filters[k[len("filters["):-1]] = vals if len(vals) > 1 else vals[0]
            if k.startswith("exclude[") and k.endswith("]"):
                excludes[k[len("exclude["):-1]] = vals if len(vals) > 1 else vals[0]

        # 3) базовый queryset
        qs = DatasetRow.objects.filter(dataset_id=ds_id)

        # 4) валидные ключи (семпл)
        sample = qs.values_list("data", flat=True)[:1000]
        valid_keys = set()
        for d in sample:
            if isinstance(d, dict):
                valid_keys.update(d.keys())
        valid_keys = list(valid_keys)

        try:
            payload = _aggregate_core(
                qs=qs,
                valid_keys=valid_keys,
                group_by=group_by,
                metric=metric,
                date_field=date_field,
                date_from=date_from,
                date_to=date_to,
                filters=filters,
                excludes=excludes,
            )
        except ValueError as e:
            return Response({"detail": str(e)}, status=400)

        return Response(payload)
