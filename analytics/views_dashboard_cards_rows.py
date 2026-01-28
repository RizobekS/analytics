# analytics/views_dashboard_cards_rows.py
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from django.db.models import QuerySet

from ingest.models import HandleRegistry, DatasetRow, Dataset, Workbook
from .views_common import user_can_edit_handle
from .views_resolve import (
    parse_client_date,
    format_client_date,
)


def _is_empty_cell(c):
    """Пуста ли ячейка Luckysheet: None, '' или {} без содержимого."""
    if c is None:
        return True
    if c == "":
        return True
    if isinstance(c, dict):
        # у Luckysheet полезные поля обычно 'v' или 'm'
        return not any(k in c and c[k] not in (None, "") for k in ("v", "m"))
    return False


def _trim_row_right(row):
    """Обрезать справа полностью пустые ячейки (чтобы не таскать кучу {})."""
    if not isinstance(row, list):
        return row
    i = len(row) - 1
    while i >= 0 and _is_empty_cell(row[i]):
        i -= 1
    return row[: i + 1]


def _row_is_all_empty(row):
    """Вся ли строка пуста (после обрезки справа)."""
    row = _trim_row_right(row)
    if not row:
        return True
    return all(_is_empty_cell(c) for c in row)


def _compact_grid(grid, max_rows=None, trim=True):
    """
    Урезать 2D-сетку Luckysheet: взять первые max_rows строк
    и/или почистить пустые хвосты строк и пустые нижние строки.
    """
    if not isinstance(grid, list):
        return grid

    # 1) срез по строкам
    if isinstance(max_rows, int) and max_rows >= 0:
        grid = grid[:max_rows]

    if not trim:
        return grid

    # 2) обрезаем пустые ячейки справа в каждой строке
    grid = [_trim_row_right(r if isinstance(r, list) else [r]) for r in grid]

    # 3) убираем полностью пустые строки снизу
    j = len(grid) - 1
    while j >= 0 and _row_is_all_empty(grid[j]):
        j -= 1
    grid = grid[: j + 1]
    return grid


def _shrink_luckysheet(luckysheet_obj, max_rows=None, trim=True):
    """
    Вернуть копию luckysheet с урезанным количеством строк.
    Поддерживаем 2 формы:
      A) {"data": [[...], [...], ...]}  # single-sheet object
      B) [{"data": [[...], ...], "name": "Sheet1"}, ...]  # массив листов (берём первый)
    """
    # B) массив листов
    if isinstance(luckysheet_obj, list):
        if not luckysheet_obj:
            return luckysheet_obj
        first = dict(luckysheet_obj[0]) if isinstance(luckysheet_obj[0], dict) else {}
        grid = first.get("data")
        if isinstance(grid, list) and (not grid or isinstance(grid[0], list)):
            first["data"] = _compact_grid(grid, max_rows=max_rows, trim=trim)
        # собираем назад
        new_ls = [first]
        return new_ls

    # A) объект одного листа
    if isinstance(luckysheet_obj, dict):
        new_ls = dict(luckysheet_obj)
        grid = new_ls.get("data")
        if isinstance(grid, list) and (not grid or isinstance(grid[0], list)):
            new_ls["data"] = _compact_grid(grid, max_rows=max_rows, trim=trim)
        return new_ls

    # прочие случаи — возвращаем как есть
    return luckysheet_obj


def _extract_data(row):
    """
    Приводим row.data к «чистому» формату без обёрток:
    - {"parsed": [...]}     -> [...]
    - {"data":   [...]}     -> [...]   (легаси)
    - {"meta": {...}, ...}  -> ... без meta
    - list/tuple            -> как есть
    - иные типы             -> как есть
    """
    data = row.data
    if data is None:
        return {}
    if isinstance(data, (list, tuple)):
        return list(data)
    if isinstance(data, dict):
        if "parsed" in data and isinstance(data["parsed"], (list, tuple)):
            return list(data["parsed"])
        if "data" in data and isinstance(data["data"], (list, tuple)):
            return list(data["data"])
        data = dict(data)
        data.pop("meta", None)
        return data
    return data


def _get_approved_dataset_for_workbook(wb: Workbook):
    """
    Возвращает (ds or None) где ds.status == 'approved'
    для указанного workbook.
    """
    return (
        Dataset.objects
        .filter(sheet__workbook=wb, status=Dataset.STATUS_APPROVED)
        .order_by("-created_at", "-id")
        .first()
    )


def _scan_for_first_approved(wb_qs):
    """
    По списку workbook'ов (итерация в порядке, в котором qs предоставляет),
    вернуть (wb, ds_approved) для первого workbook, у которого есть approved датасет.
    Если не нашли — (None, None).
    """
    for wb in wb_qs:
        ds = _get_approved_dataset_for_workbook(wb)
        if ds:
            return wb, ds
    return None, None


def _resolve_best_approved_for_handle_date(handle: str, date_str: str | None):
    """
    Логика выбора карточки для дашборда:

    1. Если пришла дата (target_date):
        a) ищем workbook с period_date <= target_date, сортировка по period_date DESC.
           Берём первый у кого есть approved датасет.
        b) если не нашли (значит дата раньше самого первого периода),
           берём САМЫЙ РАННИЙ workbook (ASC) с approved.

    2. Если дата не пришла:
        a) берём все workbook по убыванию даты (DESC), пропуская те,
           где есть только draft.
        b) если не нашли (теоретически все только draft),
           берём по возрастанию даты (ASC) первый, у кого есть approved.

    Возвращает (wb, ds_approved) или (None, None) если нет ни одного approved вообще.
    """
    target_date = parse_client_date(date_str) if date_str else None

    # кейс: дата указана
    if target_date:
        # шаг a: ищем самый свежий <= этой даты
        qs_desc = (
            Workbook.objects
            .filter(handle=handle, period_date__lte=target_date)
            .order_by("-period_date", "-id")
        )
        wb, ds = _scan_for_first_approved(qs_desc)
        if wb and ds:
            return wb, ds

        # шаг b: дата раньше всех периодов -> берём самый первый (минимальный период)
        qs_asc = (
            Workbook.objects
            .filter(handle=handle)
            .order_by("period_date", "id")
        )
        wb, ds = _scan_for_first_approved(qs_asc)
        return wb, ds

    # кейс: дата не указана
    # шаг a: самое свежее approved
    qs_desc_all = (
        Workbook.objects
        .filter(handle=handle)
        .order_by("-period_date", "-id")
    )
    wb, ds = _scan_for_first_approved(qs_desc_all)
    if wb and ds:
        return wb, ds

    # шаг b: fallback — самый ранний approved (теоретически если все свежие черновики)
    qs_asc_all = (
        Workbook.objects
        .filter(handle=handle)
        .order_by("period_date", "id")
    )
    wb, ds = _scan_for_first_approved(qs_asc_all)
    return wb, ds


class DashboardCardsRowsView(APIView):
    """
    GET /api/dashboard/cards/rows/?rows=all&rows_limit=5000&date=DD.MM.YYYY&group=...&handles=h1,h2

    Что делает:
    - отдаём карточки дашборда по хэндлам;
    - показываем ТОЛЬКО approved данные (draft никогда не уходит в дашборд);
    - выбор периода:
        * если дата указана → closest <= дате (approved); если нет — самая первая approved;
        * если дата не указана → самая свежая approved; если нет свежей approved
          (т.е. последний период только draft), берём предыдущий approved.
    - если для handle нет approved вообще → карточка не попадёт в results.
    """
    permission_classes = [IsAuthenticated]

    def get(self, request):
        date_str = request.query_params.get("date")
        group = (request.query_params.get("group") or "").strip()
        handles_param = (request.query_params.get("handles") or "").strip()
        include = set((request.query_params.get("include") or "").split(",")) if request.query_params.get("include") else set()
        # latest оставляем для обратной совместимости: влияет только на payload["data"] (одна последняя строка)
        latest = request.query_params.get("latest") in ("1", "true", "yes")
        rows_mode = (request.query_params.get("rows") or "none").lower()  # none|all
        rows_limit = int(request.query_params.get("rows_limit") or 5000)
        rows_limit = max(1, min(50000, rows_limit))

        # основной queryset хэндлов, только видимые
        qs = HandleRegistry.objects.filter(visible=True)
        if group:
            qs = qs.filter(group=group)
        if handles_param:
            hs = [h.strip() for h in handles_param.split(",") if h.strip()]
            if hs:
                qs = qs.filter(handle__in=hs)

        results = []

        for hr in qs.order_by("order_index", "handle"):
            # ищем лучшую approved-версию для этого handle и даты
            wb, ds = _resolve_best_approved_for_handle_date(hr.handle, date_str)

            # если вообще нет approved по этому handle -> не добавляем карточку
            if not wb or not ds:
                continue

            period = getattr(wb, "period_date", None)

            payload = {
                "handle": hr.handle,
                "title": hr.title or hr.handle,
                "order_index": hr.order_index,
                "group": hr.group,
                "table_kind": getattr(hr, "table_kind", "legacy"),
                "period": format_client_date(period),
                "status": ds.status,     # всегда 'approved' здесь
                "version": ds.version,
                "icon": hr.icon,
                "color": hr.color,
            }

            # доступы
            payload["editable"] = user_can_edit_handle(request.user, hr.handle)
            payload["can_upload"] = payload["editable"]
            payload["allowed_user_ids"] = list(hr.allowed_users.values_list("email", flat=True))

            # данные строк
            rows_qs: QuerySet = DatasetRow.objects.filter(dataset_id=ds.id).order_by("id")

            if latest:
                row = rows_qs.last()
                payload["id"] = row.id if row else None
                payload["data"] = _extract_data(row) if row else {}
                payload["imported_at"] = row.imported_at if row else None

            if rows_mode == "all":
                rows = [
                    {"id": r.id, "data": _extract_data(r), "imported_at": r.imported_at}
                    for r in rows_qs[:rows_limit]
                ]
                payload["rows"] = rows

            results.append(payload)

        return Response({"results": results})
