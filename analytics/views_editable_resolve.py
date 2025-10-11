# analytics/views_editable_resolve.py
import json
from django.db import transaction
from rest_framework.views import APIView
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from ingest.models import (
    DatasetRow, DatasetRowRevision,
    Workbook, Sheet, Dataset, HandleRegistry
)
from .views_resolve import parse_client_date, format_client_date


# ---------------------------
# Helpers
# ---------------------------

def find_dataset_for(handle: str, date_str: str | None):
    """Найти dataset (последний по created_at) для handle+date. Без создания."""
    target_date = parse_client_date(date_str) if date_str else None
    wb_qs = Workbook.objects.filter(handle=handle)
    if target_date:
        wb_qs = wb_qs.filter(period_date__isnull=False, period_date__lte=target_date)
    wb = wb_qs.order_by("-period_date", "-id").first()
    if not wb:
        raise Workbook.DoesNotExist(f"No workbook for handle={handle}, date={date_str or 'latest'}")
    ds = (Dataset.objects
          .filter(sheet__workbook=wb)
          .order_by("-created_at", "-id")
          .first())
    if not ds:
        raise Dataset.DoesNotExist(f"No dataset for workbook={wb.id}")
    return ds.id, ds


@transaction.atomic
def get_or_create_dataset_for(handle: str, date_str: str | None):
    """
    Находит Workbook по handle+дата и возвращает (dataset_id, Dataset).
    Если Dataset отсутствует — создаёт draft Dataset (пустой).
    """
    target_date = parse_client_date(date_str) if date_str else None
    wb_qs = Workbook.objects.filter(handle=handle)
    if target_date:
        wb_qs = wb_qs.filter(period_date__isnull=False, period_date__lte=target_date)
    wb = wb_qs.order_by("-period_date", "-id").first()
    if not wb:
        raise Workbook.DoesNotExist(f"No workbook for handle={handle}, date={date_str or 'latest'}")

    # Если уже есть датасет для этого workbook — возвращаем его
    ds = (Dataset.objects
          .filter(sheet__workbook=wb)
          .order_by("-created_at", "-id")
          .first())
    if ds:
        return ds.id, ds

    # создаём Sheet при необходимости
    sh = Sheet.objects.filter(workbook=wb).order_by("index", "id").first()
    if not sh:
        sh = Sheet.objects.create(workbook=wb, name=(wb.sheets or "Sheet1") or "Sheet1", index=0)

    ds = Dataset.objects.create(
        sheet=sh,
        name=f"{wb.filename} :: {sh.name}",
        meta={"editable": True},
        status=Dataset.STATUS_DRAFT,
        version=1,
        period_date=wb.period_date,
    )
    return ds.id, ds


# ---------------------------
# Views
# ---------------------------

class ResolveOrCreateWorkbookView(APIView):
    """
    POST /api/workbooks/resolve-or-create/
    payload:
      { "handle": "<slug>", "period_date": "DD.MM.YYYY|YYYY-MM-DD",
        "sheet_name": "Sheet1" (опц.) }

    Если Workbook(handle, period_date) уже есть → вернём связанный Dataset (существующий).
    Если нет → создадим Workbook + Sheet + Dataset(draft).
    """
    permission_classes = [IsAuthenticated]

    @transaction.atomic
    def post(self, request):
        handle = (request.data.get("handle") or "").strip()
        filename = (request.data.get("filename") or "").strip()
        period_date = parse_client_date(request.data.get("period_date"))
        sheet_name = (request.data.get("sheet_name") or "Sheet1").strip()

        if not handle or not period_date:
            return Response({"detail": "handle and period_date are required"}, status=400)

        # handle должен существовать (заранее заведён в админке)
        if not Workbook.objects.filter(handle=handle).exists():
            return Response({"detail": "unknown handle; ask admin to register this handle first"}, status=400)

        # 1) если filename не передали — подставим умно
        if not filename:
            # a) пробуем взять из предыдущего workbook по этому handle
            sample_wb = (Workbook.objects
                         .filter(handle=handle)
                         .exclude(period_date=period_date)  # на всякий случай
                         .order_by("-uploaded_at", "-id")
                         ).first()
            if sample_wb and sample_wb.filename:
                filename = sample_wb.filename
            else:
                # b) берём из HandleRegistry, если есть, иначе сам handle
                hr = HandleRegistry.objects.filter(handle=handle).first()
                base = (hr.title or "").strip() if hr and hr.title else handle
                filename = f"{base} — {format_client_date(period_date)}"

        # 2) ищем workbook на эту дату
        wb = (Workbook.objects
              .filter(handle=handle, period_date=period_date)
              .order_by("-id").first())

        if not wb:
            # создаём workbook с вычисленным filename
            wb = Workbook.objects.create(
                filename=filename,
                sha256="manual",
                uploaded_by=request.user,
                status=Workbook.STATUS_READY,
                handle=handle,
                period_date=period_date,
                sheets=sheet_name
            )

        # 3) лист
        sh = Sheet.objects.filter(workbook=wb).order_by("index", "id").first()
        if not sh:
            sh = Sheet.objects.create(workbook=wb, name=sheet_name, index=0)

        # 4) датасет: НЕ создаём новый, если уже есть; берём последний по created_at
        ds = (Dataset.objects
              .filter(sheet__workbook=wb)
              .order_by("-created_at", "-id")
              .first())

        if not ds:
            ds = Dataset.objects.create(
                sheet=sh,
                name=f"{wb.filename} :: {sh.name}",
                meta={"editable": True},
                status=Dataset.STATUS_DRAFT,
                version=1,
                period_date=period_date,
            )

        return Response({
            "workbook_id": wb.id,
            "dataset_id": ds.id,
            "handle": wb.handle,
            "period_date": format_client_date(wb.period_date),
            "status": ds.status,
            "version": ds.version,
            "dataset_name": ds.name,
            "filename": wb.filename,
        }, status=200)


class EditableResolveSchemaView(APIView):
    """GET /api/editable/resolve/schema/?handle=<slug>&date=DD.MM.YYYY"""
    permission_classes = [IsAuthenticated]

    def get(self, request):
        handle = (request.query_params.get("handle") or "").strip()
        date_str = request.query_params.get("date")
        if not handle:
            return Response({"detail": "param 'handle' is required"}, status=400)

        try:
            dataset_id, _ = get_or_create_dataset_for(handle, date_str)
        except Workbook.DoesNotExist:
            return Response({"detail": "workbook not found for given handle/date"}, status=404)

        return Response({"dataset_id": dataset_id, "columns": []})


class EditableResolveRowsView(APIView):
    """
    POST /api/editable/resolve/rows/?handle=<slug>&date=DD.MM.YYYY

    Если датасет существует — обновляем его.
    Если Luckysheet уже был — перезаписываем последнюю строку (update).
    Если строки нет — создаём первую.
    """
    permission_classes = [IsAuthenticated]

    @transaction.atomic
    def post(self, request):
        handle = (request.query_params.get("handle") or "").strip()
        date_str = request.query_params.get("date")
        if not handle:
            return Response({"detail": "param 'handle' is required"}, status=400)

        try:
            dataset_id, ds = get_or_create_dataset_for(handle, date_str)
        except Workbook.DoesNotExist:
            return Response({"detail": "workbook not found for given handle/date"}, status=404)

        luckysheet_payload = request.data.get("luckysheet")
        if luckysheet_payload is None:
            return Response({"detail": "luckysheet payload required"}, status=400)

        if isinstance(luckysheet_payload, str):
            try:
                luckysheet_payload = str(luckysheet_payload)
            except Exception:
                return Response({"detail": "luckysheet must be a valid string"}, status=400)

        # проверим — есть ли уже строка
        existing_row = DatasetRow.objects.filter(dataset_id=dataset_id).order_by("-id").first()

        if existing_row:
            before = existing_row.data
            existing_row.data = {"luckysheet": luckysheet_payload}
            existing_row.save(update_fields=["data"])
            DatasetRowRevision.objects.create(
                row=existing_row,
                version=existing_row.revisions.count() + 1,
                data_before=before,
                data_after=existing_row.data,
                changed_by=request.user
            )
            saved_id = existing_row.id
        else:
            r = DatasetRow.objects.create(dataset_id=dataset_id, data={"luckysheet": luckysheet_payload})
            DatasetRowRevision.objects.create(
                row=r,
                version=1,
                data_before={},
                data_after=r.data,
                changed_by=request.user
            )
            saved_id = r.id

        return Response({
            "dataset_id": dataset_id,
            "saved_ids": [saved_id],
            "status": "updated" if existing_row else "created"
        }, status=200)
