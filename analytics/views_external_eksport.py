# analytics/views_external_eksport.py
from rest_framework.views import APIView
from rest_framework.response import Response
from django.conf import settings

from analytics.permissions import IsAuthenticatedOrApiKey
from ingest.models import Workbook, Dataset, DatasetRow, HandleRegistry
from analytics.views_resolve import (
    parse_client_date,
    format_client_date,
    _merge_rows_data,
    _pick_dataset_by_status,
)

HANDLE = "1-eksport"


class ExternalEksportRowsView(APIView):
    """
    GET /api/external/1-eksport/rows/
      [&date_from=DD.MM.YYYY] [&date_to=DD.MM.YYYY]
      [&status=approved|draft|all|latest]
      [&aggregate=1|0]  default: 1
      [&rows=none|all]  (только для aggregate=1)
      [&page_size=100] [&offset=0]
      плюс параметры как в ResolveRowsView для aggregate=0: limit/start_row/single

    Каждый элемент results[] возвращается в формате /api/datasets/resolve/rows/
    (только принудительно для handle=1-eksport).
    """
    permission_classes = [IsAuthenticatedOrApiKey]

    def get(self, request):

        date_from = parse_client_date(request.query_params.get("date_from"))
        date_to = parse_client_date(request.query_params.get("date_to"))

        status_param = (request.query_params.get("status") or "latest").lower()
        aggregate = str(request.query_params.get("aggregate") or "1").lower() in ("1", "true", "yes")
        rows_mode = (request.query_params.get("rows") or "none").lower()  # none|all

        # пагинация по периодам
        try:
            page_size = int(request.query_params.get("page_size") or 100)
            offset = int(request.query_params.get("offset") or 0)
        except ValueError:
            page_size, offset = 100, 0
        page_size = max(1, min(500, page_size))
        offset = max(0, offset)

        wb_qs = Workbook.objects.filter(handle=HANDLE).order_by("-period_date", "-id")
        if date_from:
            wb_qs = wb_qs.filter(period_date__isnull=False, period_date__gte=date_from)
        if date_to:
            wb_qs = wb_qs.filter(period_date__isnull=False, period_date__lte=date_to)

        total = wb_qs.count()
        wb_qs = wb_qs[offset: offset + page_size]

        hr = HandleRegistry.objects.filter(handle=HANDLE).only(
            "title", "order_index", "group", "icon", "color"
        ).first()

        results = []
        for wb in wb_qs:
            # датасет для конкретного периода + статус
            ds_qs = Dataset.objects.filter(sheet__workbook=wb).order_by("-created_at", "-id")
            if status_param == "approved":
                ds = ds_qs.filter(status=Dataset.STATUS_APPROVED).first()
            elif status_param == "draft":
                ds = ds_qs.filter(status=Dataset.STATUS_DRAFT).first()
            elif status_param == "all":
                ds = ds_qs.first()
            else:
                # latest (старое поведение) — через общий хелпер
                ds = _pick_dataset_by_status(wb, "latest")

            if not ds:
                # нет датасета для периода → пропускаем (можно возвращать пустой объект, если надо)
                continue

            meta = {
                "handle": HANDLE,
                "title": (hr.title if hr and hr.title else HANDLE),
                "order_index": (hr.order_index if hr else None),
                "group": (hr.group if hr else ""),
                "period": format_client_date(getattr(wb, "period_date", None)),
                "status": ds.status,
                "version": ds.version,
                "icon": (hr.icon if hr else ""),
                "color": (hr.color if hr else ""),
            }

            if aggregate:
                rows_qs = DatasetRow.objects.filter(dataset_id=ds.id).order_by("id")
                rows = list(rows_qs)
                merged = _merge_rows_data(rows)
                latest_row = rows[-1] if rows else None

                obj = {
                    "id": latest_row.id if latest_row else None,
                    "data": merged,
                    "imported_at": latest_row.imported_at if latest_row else None,
                    "rows_count": len(rows),
                }
                if rows_mode == "all":
                    obj["rows"] = [{"id": r.id, "data": (r.data or {}), "imported_at": r.imported_at} for r in rows]

                meta.update(obj)
                results.append(meta)
                continue

            # aggregate=0: возвращаем rows как список (как в ResolveRowsView)
            try:
                limit = int(request.query_params.get("limit", 5000))
            except ValueError:
                limit = 5000
            limit = max(1, min(50000, limit))
            try:
                start_row = int(request.query_params.get("start_row", 0))
            except ValueError:
                start_row = 0

            qs = DatasetRow.objects.filter(dataset_id=ds.id).order_by("id")
            if start_row > 0:
                qs = qs.filter(id__gte=start_row)
            qs = qs[:limit]
            rows = [{"id": r.id, "data": (r.data or {}), "imported_at": r.imported_at} for r in qs]

            # чтобы формат был “как resolve/rows”, просто кладём rows массив внутрь объекта периода
            meta["rows"] = rows
            meta["rows_count"] = len(rows)
            results.append(meta)

        return Response({
            "handle": HANDLE,
            "count": total,
            "offset": offset,
            "page_size": page_size,
            "results": results,
        })
