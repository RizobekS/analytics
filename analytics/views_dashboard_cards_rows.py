# analytics/views_dashboard_cards_rows.py
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from django.db.models import QuerySet

from ingest.models import HandleRegistry, DatasetRow, Dataset
from .views_resolve import resolve_dataset_id, parse_client_date, format_client_date


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
        # остальные листы не трогаем (можно убрать, если важно сильнее ужать)
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


class DashboardCardsRowsView(APIView):
    """
    GET /api/dashboard/cards/rows?latest=1
    GET /api/dashboard/cards/rows?date=DD.MM.YYYY
      [&group=<name>]
      [&handles=a,b,c]
      [&include=schema,style]
      [&only_with_dataset=1]
      [&row=latest|first]         # какую строку подставлять (по умолчанию latest)
      [&orws_limit=<N>]                # сколько строк вернуть внутри data
      [&trim=0|1]                 # обрезать пустые хвосты (по умолчанию 1)

    Возвращает отсортированный список карточек без массива rows.
    Внутри карточки: "id", "data", "imported_at" (одной строки — latest/first).
    Если в data.luckysheet присутствует сетка, она будет урезана по limit и очищена от пустых хвостов.
    """

    permission_classes = [IsAuthenticated]

    def get(self, request):
        date_str = request.query_params.get("date")
        _ = parse_client_date(date_str) if date_str else None

        group = (request.query_params.get("group") or "").strip()
        handles_param = (request.query_params.get("handles") or "").strip()
        only_with_dataset = request.query_params.get("only_with_dataset") in ("1", "true", "yes")
        include = set((request.query_params.get("include") or "").split(",")) if request.query_params.get("include") else set()

        # режим одной строки (как раньше): latest|first
        row_mode = (request.query_params.get("row") or "latest").lower()
        if row_mode not in ("latest", "first"):
            row_mode = "latest"

        # НОВОЕ: вернуть весь набор строк?
        rows_mode = (request.query_params.get("rows") or "none").lower()  # none|all
        if rows_mode not in ("none", "all"):
            rows_mode = "none"

        # лимиты/порядок для rows=all
        try:
            rows_limit = int(request.query_params.get("rows_limit") or 5000)
        except ValueError:
            rows_limit = 5000
        rows_limit = max(1, min(50000, rows_limit))

        rows_order = (request.query_params.get("rows_order") or "asc").lower()
        if rows_order not in ("asc", "desc"):
            rows_order = "asc"

        try:
            grid_limit = request.query_params.get("limit")
            max_rows = int(grid_limit) if grid_limit is not None else None
        except ValueError:
            max_rows = None
        trim = request.query_params.get("trim")
        trim = True if trim is None else (str(trim).lower() in ("1", "true", "yes"))

        qs = HandleRegistry.objects.filter(visible=True)
        if group:
            qs = qs.filter(group=group)
        if handles_param:
            hs = [h.strip() for h in handles_param.split(",") if h.strip()]
            if hs:
                qs = qs.filter(handle__in=hs)

        results = []
        for hr in qs.order_by("order_index", "handle"):
            # 1) резолвим dataset для handle+дата
            try:
                dataset_id = resolve_dataset_id(hr.handle, date_str)
            except Exception:
                if only_with_dataset:
                    continue
                results.append({
                    "handle": hr.handle,
                    "title": hr.title or hr.handle,
                    "order_index": hr.order_index,
                    "group": hr.group,
                    "period": None,
                    "status": None,
                    "version": None,
                    "icon": hr.icon,
                    "color": hr.color,
                })
                continue

            # 2) мета
            ds = Dataset.objects.select_related("sheet__workbook").only("id", "status", "version", "sheet_id").get(id=dataset_id)
            period = getattr(ds.sheet.workbook, "period_date", None)

            payload = {
                "handle": hr.handle,
                "title": hr.title or hr.handle,
                "order_index": hr.order_index,
                "group": hr.group,
                "period": format_client_date(period),
                "status": ds.status,
                "version": ds.version,
                "icon": hr.icon,
                "color": hr.color,
            }

            # 3а) одна строка (совместимость)
            row = None
            if row_mode == "latest":
                row = DatasetRow.objects.filter(dataset_id=dataset_id).order_by("-id").first()
            else:
                row = DatasetRow.objects.filter(dataset_id=dataset_id).order_by("id").first()
            if row:
                payload["id"] = row.id
                payload["data"] = row.data or {}
                payload["imported_at"] = row.imported_at

            # 3б) НОВОЕ: полный массив строк (по запросу rows=all)
            if rows_mode == "all":
                qs_rows: QuerySet = DatasetRow.objects.filter(dataset_id=dataset_id)
                qs_rows = qs_rows.order_by("id" if rows_order == "asc" else "-id")[:rows_limit]
                rows = [{"id": r.id, "data": (r.data or {}), "imported_at": r.imported_at} for r in qs_rows]
                payload["rows"] = rows

            if "schema" in include:
                payload["schema"] = {"columns": []}
            if "style" in include:
                payload["style"] = getattr(hr, "style_json", {}) or {}

            results.append(payload)

        return Response({"results": results})
