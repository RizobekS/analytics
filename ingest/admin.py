# ingest/admin.py
from django.contrib import admin, messages
from django.db.models.functions import Cast
from django.db.models import TextField
from import_export import resources
from import_export.admin import ImportExportModelAdmin
from django.urls import path
from django.shortcuts import redirect
from django.utils.html import format_html

from .models import Workbook, Dataset, DatasetRow, DataTemplate, ColumnMapping, DatasetRowRevision, HandleRegistry, \
    UploadHistory
from analytics.tasks import import_excel_task


# === DataTemplate & ColumnMapping ===

class ColumnMappingInline(admin.TabularInline):
    model = ColumnMapping
    extra = 1
    fields = ("canonical_key", "aliases", "dtype", "required", "min_value", "max_value", "regex", "choices")
    show_change_link = True

@admin.register(DataTemplate)
class DataTemplateAdmin(admin.ModelAdmin):
    list_display = ("name", "mappings_count", "required_count", "created_at")
    search_fields = ("name",)
    inlines = [ColumnMappingInline]

    @admin.display(description="Всего полей")
    def mappings_count(self, obj):
        return obj.mappings.count()

    @admin.display(description="Обязательных")
    def required_count(self, obj):
        return obj.mappings.filter(required=True).count()


@admin.register(HandleRegistry)
class HandleRegistryAdmin(admin.ModelAdmin):
    list_display  = ("handle", "title", "order_index", "group", "visible")
    list_editable = ("title", "order_index", "group", "visible")
    search_fields = ("handle", "title", "group")
    filter_horizontal = ("allowed_users",)

    fields = (
        "handle", "title", "order_index", "group", "visible",
        "icon", "color", "style_json",
        "allowed_users",
    )


# ---------- EXPORT ----------
class DatasetRowResource(resources.ModelResource):
    """
    Экспортируем плоско: id, dataset_id и JSON data.
    """
    class Meta:
        model = DatasetRow
        fields = ("id", "dataset__id", "data",)
        export_order = ("id", "dataset__id", "data",)


@admin.register(DatasetRow)
class DatasetRowAdmin(ImportExportModelAdmin):
    resource_classes = [DatasetRowResource]
    list_display = ("id", "dataset", "imported_at", "short_data")
    list_filter = ("dataset",)
    date_hierarchy = "imported_at"

    @admin.display(description="data (short)")
    def short_data(self, obj):
        s = str(obj.data)[:120].replace("{", "").replace("}", "")
        return s + ("..." if len(str(obj.data)) > 120 else "")

    # Кастомный поиск по JSON как тексту
    def get_search_results(self, request, queryset, search_term):
        qs, use_distinct = super().get_search_results(request, queryset, search_term)
        if search_term:
            qs = qs.annotate(data_str=Cast("data", output_field=TextField())).filter(
                data_str__icontains=search_term
            )
        return qs, use_distinct


@admin.action(description="Опубликовать выбранные датасеты (draft → approved)")
def publish_datasets(modeladmin, request, queryset):
    updated = 0
    for ds in queryset:
        if ds.status != Dataset.STATUS_APPROVED:
            ds.status = Dataset.STATUS_APPROVED
            # версию можно увеличивать по вашей бизнес-логике
            ds.version = ds.version or 1
            ds.save(update_fields=["status", "version"])
            updated += 1
    messages.success(request, f"Опубликовано: {updated} датасетов")


@admin.register(Dataset)
class DatasetAdmin(admin.ModelAdmin):
    list_display = ("name", "id", "sheet", "status", "version", "created_at", "rows_count")
    list_filter  = ("status", "sheet__workbook__handle")
    search_fields = ("name",)
    fields = ("name", "sheet", "period_date", "status", "inferred_schema", "primary_key", "meta")

    actions = [publish_datasets]

    def rows_count(self, obj):

        return obj.rows.count()


@admin.register(DatasetRowRevision)
class DatasetRowRevisionAdmin(admin.ModelAdmin):
    list_display = ("id", "row_id", "version", "changed_by", "changed_at")
    list_filter  = ("changed_by",)
    readonly_fields = ("row", "version", "data_before", "data_after", "changed_by", "changed_at")


@admin.register(UploadHistory)
class UploadHistoryAdmin(admin.ModelAdmin):
    list_display = ("user", "handle", "period_date", "action", "created_at")
    list_filter  = ("user",)
    readonly_fields = ("user", "workbook", "dataset", "status_before", "status_after", "created_at")


@admin.action(description="Импортировать выбранные таблицы")
def import_selected_workbooks(modeladmin, request, queryset):
    scheduled, skipped = 0, 0
    # заранее подгружаем template, чтобы не дёргать БД в цикле
    for wb in queryset.select_related("template"):
        # защита от пустого файла / параллельного импорта
        if not getattr(wb, "file", None) or not wb.file:
            skipped += 1
            continue
        if getattr(wb, "status", "") == "importing":
            skipped += 1
            continue

        import_excel_task.delay(
            workbook_id=wb.id,
            sheet_name=wb.sheets or "",
            bulk_size=5000,  # можно поменять при желании
            template=(wb.template.name if wb.template_id else ""),
            header_row=(wb.header_row or 0),
            auto_template=bool(wb.auto_template),
        )
        scheduled += 1

    if scheduled:
        modeladmin.message_user(
            request,
            f"Импорт запущен для {scheduled} таблиц(ы).",
            level=messages.SUCCESS,
        )
    if skipped:
        modeladmin.message_user(
            request,
            f"Пропущено {skipped}: нет файла или статус 'importing'.",
            level=messages.WARNING,
        )


# ---------- UPLOAD + IMPORT ----------
@admin.register(Workbook)
class WorkbookAdmin(admin.ModelAdmin):
    list_display = ("id", "filename", "handle", "status", "period_date", "template", "auto_template", "sha256_short", "uploaded_at")
    list_filter = ("status", "template", "auto_template")
    search_fields = ("filename", "handle")
    fields = (
        "file", "filename", "status", "sha256", "handle", "period_date",
        "template", "auto_template", "sheets", "header_row",
    )
    readonly_fields = ("status", "sha256")
    actions = [import_selected_workbooks]

    def sha256_short(self, obj):
        return (obj.sha256 or "")[:12]
    sha256_short.short_description = "SHA256"

    # Кнопка «Импортировать» на change-странице
    def change_view(self, request, object_id, form_url="", extra_context=None):
        extra_context = extra_context or {}
        extra_context["import_button"] = True
        return super().change_view(request, object_id, form_url, extra_context=extra_context)

    def get_urls(self):
        urls = super().get_urls()
        custom = [
            path("<int:pk>/import/", self.admin_site.admin_view(self.import_view), name="workbook-import"),
        ]
        return custom + urls

    def import_view(self, request, pk):
        wb = self.get_object(request, pk)
        if not wb:
            self.message_user(request, "Workbook не найден", level=messages.ERROR)
            return redirect("..")

        # берём настройки из модели (и из query-параметров, если переданы явно)
        sheet_name = request.GET.get("sheet", "") or (wb.sheet or "")
        header_row = request.GET.get("header_row")
        header_row = int(header_row) if header_row not in (None, "",) else (wb.header_row or 0)

        template = ""
        if wb.template_id:
            # можно передать имя или id — наша команда поддерживает оба варианта
            template = wb.template.name

        auto_template = wb.auto_template
        # запустить Celery-таск
        import_excel_task.delay(
            workbook_id=wb.id,
            sheet_name=sheet_name,
            bulk_size=5000,
            template=template,
            header_row=header_row or 0,
            auto_template=auto_template,
        )
        self.message_user(request, "Импорт запущен", level=messages.SUCCESS)
        return redirect("..")
