# analytics/tasks.py
from celery import shared_task
from django.core.management import call_command

@shared_task(bind=True)
def import_excel_task(
    self,
    workbook_id: int,
    sheet_name: str = "",
    bulk_size: int = 5000,
    template: str = "",
    header_row: int = 0,
    auto_template: bool = True,
):
    """
    Запускает management-команду import_excel с параметрами, взятыми из Workbook.
    """
    opts = {
        "workbook_id": workbook_id,
        "bulk_size": int(bulk_size),
    }
    if sheet_name:
        opts["sheet_name"] = sheet_name
    if header_row and int(header_row) > 0:
        opts["header_row"] = int(header_row)
    if template:
        opts["template"] = template
    if not auto_template:
        opts["no_auto_template"] = True

    # Важно: path не передаём — команда сама возьмёт wb.file.path по workbook_id
    call_command("import_excel", **opts)
    return {"ok": True, "workbook_id": workbook_id}
