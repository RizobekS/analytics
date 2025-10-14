# analytics/views_resolve.py
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from datetime import datetime

from ingest.models import Workbook, Dataset, DatasetRow, HandleRegistry


# ---------------------------
# Date helpers (DD.MM.YYYY <-> date)
# ---------------------------
def _merge_rows_data(rows):
    """
    Слить несколько DatasetRow в один словарь.
    - Берём ТОЛЬКО dict-подобные data.
    - Если внутри data лежит {"parsed": {...}}, то берём data["parsed"].
    - Идём от старых к новым, чтобы новые значения перезаписывали старые.
    """
    merged = {}
    for r in reversed(rows):  # старые → новые
        d = r.data or {}
        if isinstance(d, dict) and "parsed" in d and isinstance(d["parsed"], dict):
            d = d["parsed"]
        if isinstance(d, dict):
            merged.update(d)
    return merged

def parse_client_date(s: str | None):
    if not s:
        return None
    s = s.strip()
    # DD.MM.YYYY
    try:
        return datetime.strptime(s, "%d.%m.%Y").date()
    except Exception:
        pass
    # ISO YYYY-MM-DD (fallback/back-compat)
    from django.utils.dateparse import parse_date as _parse_date
    return _parse_date(s)

def format_client_date(d):
    if not d:
        return None
    if isinstance(d, datetime):
        d = d.date()
    return d.strftime("%d.%m.%Y")


# ---------------------------
# Internal resolvers
# ---------------------------

def _get_workbook_for(handle: str, date_str: str | None):
    """
    Находим workbook по handle и (опц.) дате: берём самый свежий период <= date.
    """
    target_date = parse_client_date(date_str) if date_str else None
    qs = Workbook.objects.filter(handle=handle)
    if target_date:
        qs = qs.filter(period_date__isnull=False, period_date__lte=target_date)
    wb = qs.order_by("-period_date", "-id").first()
    if not wb:
        raise Workbook.DoesNotExist(f"No workbook for handle={handle}, date={date_str or 'latest'}")
    return wb

def _get_dataset_for_workbook_latest(wb: Workbook):
    """
    Всегда самый последний датасет для воркбука (created_at DESC, id DESC),
    без приоритета approved — «актуальная» рабочая версия.
    """
    ds = (Dataset.objects
          .filter(sheet__workbook=wb)
          .order_by("-created_at", "-id")
          .first())
    if not ds:
        raise Dataset.DoesNotExist(f"No dataset for workbook={wb.id}")
    return ds


# ---------------------------
# Public API
# ---------------------------

class WorkbookPeriodsView(APIView):
    """
    GET /api/workbooks/periods/?handle=<slug>
        [&status=approved|draft|all] (default: approved)
        [&date_from=DD.MM.YYYY] [&date_to=DD.MM.YYYY]
        [&only_with_dataset=1]
        [&limit=50] [&offset=0]

    Список доступных периодов по handle (DESC). Для каждого периода
    подставляется «лучший» датасет согласно status-фильтру.
    """
    permission_classes = [IsAuthenticated]

    def get(self, request):
        handle = (request.query_params.get("handle") or "").strip()
        if not handle:
            return Response({"detail": "param 'handle' is required"}, status=400)

        status_filter = (request.query_params.get("status") or "approved").lower()
        if not status_filter in ("approved", "draft", "all"):
            status_filter = "approved"

        date_from = parse_client_date(request.query_params.get("date_from"))
        date_to   = parse_client_date(request.query_params.get("date_to"))

        only_with_dataset = request.query_params.get("only_with_dataset") in ("1", "true", "yes")
        try:
            limit  = max(1, min(500, int(request.query_params.get("limit") or 100)))
            offset = max(0, int(request.query_params.get("offset") or 0))
        except ValueError:
            limit, offset = 100, 0

        wb_qs = Workbook.objects.filter(handle=handle)
        if date_from:
            wb_qs = wb_qs.filter(period_date__gte=date_from)
        if date_to:
            wb_qs = wb_qs.filter(period_date__lte=date_to)

        wb_qs = wb_qs.order_by("-period_date", "-id")[offset:offset+limit]

        items = []
        for wb in wb_qs:
            ds_qs = Dataset.objects.filter(sheet__workbook=wb).order_by("-created_at", "-id")
            if   status_filter == "approved": ds = ds_qs.filter(status=Dataset.STATUS_APPROVED).first()
            elif status_filter == "draft":    ds = ds_qs.filter(status=Dataset.STATUS_DRAFT).first()
            else:                             ds = ds_qs.first()  # любой, последний

            if ds is None and only_with_dataset:
                continue

            items.append({
                "workbook_id": wb.id,
                "handle": wb.handle,
                "period_date": format_client_date(wb.period_date),
                "dataset_id": ds.id if ds else None,
                "dataset_status": ds.status if ds else None,
                "dataset_version": ds.version if ds else None,
                "dataset_name": ds.name if ds else None,
            })

        return Response({"results": items})


class DatasetResolveView(APIView):
    """
    GET /api/datasets/resolve/?handle=<slug>&latest=1
    GET /api/datasets/resolve/?handle=<slug>&date=DD.MM.YYYY

    Возвращает мета по «последнему датасету» выбранного воркбука (без приоритета approved).
    """
    permission_classes = [IsAuthenticated]

    def get(self, request):
        handle = (request.query_params.get("handle") or "").strip()
        if not handle:
            return Response({"detail": "param 'handle' is required"}, status=400)

        date_str = request.query_params.get("date")
        try:
            wb = _get_workbook_for(handle, date_str)
            ds = _get_dataset_for_workbook_latest(wb)
        except Workbook.DoesNotExist:
            return Response({"detail": "workbook not found for given handle/date"}, status=404)
        except Dataset.DoesNotExist:
            return Response({"detail": "dataset not found for workbook"}, status=404)

        return Response({
            "dataset_id": ds.id,
            "workbook_id": wb.id,
            "handle": wb.handle,
            "period": format_client_date(wb.period_date),
            "status": ds.status,
            "version": ds.version,
            "dataset_name": ds.name,
        })


def resolve_dataset_id(handle: str, date_str: str | None = None) -> int:
    """
    Хелпер для других вьюх: вернуть id «последнего датасета» по handle+date.
    """
    wb = _get_workbook_for(handle, date_str)
    ds = _get_dataset_for_workbook_latest(wb)
    return ds.id


class ResolveRowsView(APIView):
    """
    GET /api/datasets/resolve/rows/?handle=<slug>&latest=1
    GET /api/datasets/resolve/rows/?handle=<slug>&date=DD.MM.YYYY
      Параметры (опц.):
        - aggregate: 0|1  (по умолчанию 1) — слить все строки в один словарь
        - limit: int      — если aggregate=0, максимум строк (по умолчанию 5000, макс. 50_000)
        - start_row: int  — id, с которого читать (только при aggregate=0)
        - single: 1       — вернуть единый объект (мета + данные)

    По умолчанию aggregate=1 → всегда "один словарь" по датасету.
    """
    permission_classes = [IsAuthenticated]

    def get(self, request):
        handle = (request.query_params.get("handle") or "").strip()
        if not handle:
            return Response({"detail": "param 'handle' is required"}, status=400)

        date_str = request.query_params.get("date")
        aggregate = str(request.query_params.get("aggregate") or "1").lower() in ("1","true","yes")
        single_mode = request.query_params.get("single") in ("1", "true", "yes")

        # workbook + latest dataset
        wb = _get_workbook_for(handle, date_str)
        ds = _get_dataset_for_workbook_latest(wb)
        dataset_id = ds.id

        if aggregate:
            rows_qs = DatasetRow.objects.filter(dataset_id=dataset_id).order_by("id")
            rows = list(rows_qs)
            merged = _merge_rows_data(rows)
            latest_row = rows[-1] if rows else None

            obj = {
                "id": latest_row.id if latest_row else None,
                "data": merged,
                "imported_at": latest_row.imported_at if latest_row else None,
            }

            # метаданные карточки
            hr = HandleRegistry.objects.filter(handle=handle).only(
                "title", "order_index", "group", "icon", "color"
            ).first()
            meta = {
                "handle": handle,
                "title": (hr.title if hr and hr.title else handle),
                "order_index": (hr.order_index if hr else None),
                "group": (hr.group if hr else ""),
                "period": format_client_date(getattr(wb, "period_date", None)),
                "status": ds.status,
                "version": ds.version,
                "icon": (hr.icon if hr else ""),
                "color": (hr.color if hr else ""),
                "rows_count": len(rows),
            }
            meta.update(obj)
            return Response(meta if single_mode or True else [meta])  # всегда один объект при aggregate=1

        # ----- aggregate=0: как раньше, массив строк, но в data — что в БД -----
        try:
            limit = int(request.query_params.get("limit", 5000))
        except ValueError:
            limit = 5000
        limit = max(1, min(50000, limit))

        try:
            start_row = int(request.query_params.get("start_row", 0))
        except ValueError:
            start_row = 0

        qs = DatasetRow.objects.filter(dataset_id=dataset_id).order_by("id")
        if start_row > 0:
            qs = qs.filter(id__gte=start_row)
        qs = qs[:limit]

        rows = [{"id": r.id, "data": (r.data or {}), "imported_at": r.imported_at} for r in qs]

        if single_mode or len(rows) == 1:
            # метаданные карточки
            row_obj = rows[0] if rows else {}
            hr = HandleRegistry.objects.filter(handle=handle).only(
                "title", "order_index", "group", "icon", "color"
            ).first()
            meta = {
                "handle": handle,
                "title": (hr.title if hr and hr.title else handle),
                "order_index": (hr.order_index if hr else None),
                "group": (hr.group if hr else ""),
                "period": format_client_date(getattr(wb, "period_date", None)),
                "status": ds.status,
                "version": ds.version,
                "icon": (hr.icon if hr else ""),
                "color": (hr.color if hr else ""),
            }
            meta.update(row_obj)
            return Response(meta)

        return Response(rows)
