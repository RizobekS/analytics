# analytics/views_resolve.py
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from datetime import datetime

from analytics.views_common import user_can_edit_handle
from ingest.models import Workbook, Dataset, DatasetRow, HandleRegistry, UploadHistory


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

def _pick_dataset_by_status(wb: Workbook, status_param: str | None):
    """
    status_param: 'approved' | 'draft' | 'latest'/None
    """
    ds_qs = Dataset.objects.filter(sheet__workbook=wb).order_by("-created_at", "-id")
    status_param = (status_param or "latest").lower()
    if status_param == "approved":
        return ds_qs.filter(status=Dataset.STATUS_APPROVED).first() or ds_qs.first()
    if status_param == "draft":
        return ds_qs.filter(status=Dataset.STATUS_DRAFT).first() or ds_qs.first()
    # latest (как раньше)
    return ds_qs.first()

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
        status_param = request.query_params.get("status")  # 'approved' | 'draft' | 'latest'
        aggregate = str(request.query_params.get("aggregate") or "1").lower() in ("1", "true", "yes")
        rows_mode = (request.query_params.get("rows") or "none").lower()  # 'none' | 'all'
        single_mode = request.query_params.get("single") in ("1", "true", "yes")

        wb = _get_workbook_for(handle, date_str)
        status_param_norm = (status_param or "latest").lower()
        if status_param_norm in ("approved", "draft"):
            ds = (Dataset.objects
                  .filter(sheet__workbook=wb,
                          status=(Dataset.STATUS_APPROVED if status_param_norm == "approved"
                                  else Dataset.STATUS_DRAFT))
                  .order_by("-created_at", "-id")
                  .first())
            if not ds:
                # НЕТ датасета с указанным статусом для этого периода → 404
                # Сообщение по сути: "эта таблица либо была подтверждена, либо не существует (в запрошенном статусе)"
                return Response(
                    {
                        "detail": (
                            f"Для handle='{handle}' и даты '{format_client_date(getattr(wb, 'period_date', None))}' "
                            f"нет версии со статусом '{status_param_norm}'."
                        )
                    },
                    status=404,
                )
        else:
            # старое поведение для status=latest/None
            ds = _pick_dataset_by_status(wb, status_param)
        # ─────────────────────────────────────────────────────────────────────────────

        if not ds:
            return Response({"detail": "dataset not found for workbook"}, status=404)

        dataset_id = ds.id

        # общая мета карточки (как в dashboard)
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

        if aggregate:
            rows_qs = DatasetRow.objects.filter(dataset_id=dataset_id).order_by("id")
            rows = list(rows_qs)
            merged = _merge_rows_data(rows)
            latest_row = rows[-1] if rows else None

            obj = {
                "id": latest_row.id if latest_row else None,
                "data": merged,
                "imported_at": latest_row.imported_at if latest_row else None,
                "rows_count": len(rows),
            }
            # rows=all → приложим и массив строк
            if rows_mode == "all":
                obj["rows"] = [{"id": r.id, "data": (r.data or {}), "imported_at": r.imported_at} for r in rows]

            meta.update(obj)
            return Response(meta)

        # aggregate=0 → как раньше: массив строк (или single объект)
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
            row_obj = rows[0] if rows else {}
            meta.update(row_obj)
            return Response(meta)

        return Response(rows)


class DatasetStatusUpdateView(APIView):
    """
    POST /api/datasets/status/
    payload варианты:
      { "dataset_id": 123, "status": "approved" }
      { "handle": "1-eksport", "date": "21.10.2025", "status": "approved" }

    Требует права редактирования handle (как на загрузку).
    """
    permission_classes = [IsAuthenticated]

    def post(self, request):
        dataset_id = request.data.get("dataset_id")
        handle = (request.data.get("handle") or "").strip()
        date_str = request.data.get("date")
        new_status = (request.data.get("status") or "").lower()

        if new_status not in (Dataset.STATUS_DRAFT, Dataset.STATUS_APPROVED):
            return Response({"detail": "status must be 'draft' or 'approved'"}, status=400)

        if dataset_id:
            try:
                ds = Dataset.objects.select_related("sheet__workbook").get(id=int(dataset_id))
                wb = ds.sheet.workbook
                handle = wb.handle
            except Exception:
                return Response({"detail": "dataset not found"}, status=404)
        else:
            if not handle:
                return Response({"detail": "handle is required (or dataset_id)"}, status=400)
            try:
                wb = _get_workbook_for(handle, date_str)
            except Workbook.DoesNotExist:
                return Response({"detail": "workbook not found for given handle/date"}, status=404)
            ds = _pick_dataset_by_status(wb, "latest")
            if not ds:
                return Response({"detail": "dataset not found for workbook"}, status=404)

        # права
        if not user_can_edit_handle(request.user, handle):
            return Response({"detail": "forbidden for this handle"}, status=403)

        before = ds.status
        if before == new_status:
            return Response({"detail": "no-op (status unchanged)"}, status=200)

        ds.status = new_status
        ds.save(update_fields=["status"])

        UploadHistory.objects.create(
            user=request.user,
            handle=handle,
            period_date=wb.period_date,
            workbook=wb,
            dataset=ds,
            filename=wb.filename,
            rows_count=ds.rows.count(),
            action=UploadHistory.ACTION_STATUS_CHANGE,
            status_before=before,
            status_after=new_status,
        )

        return Response({
            "dataset_id": ds.id,
            "handle": handle,
            "period": format_client_date(wb.period_date),
            "status_before": before,
            "status_after": new_status
        }, status=200)
