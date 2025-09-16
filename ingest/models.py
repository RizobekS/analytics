# ingest/models.py
from django.contrib.postgres.fields import ArrayField
from django.db import models
from datetime import datetime
from django.utils import timezone


class DataTemplate(models.Model):
    name = models.CharField(max_length=128, unique=True)
    description = models.TextField(blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.name


class ColumnMapping(models.Model):
    template = models.ForeignKey(
        DataTemplate, on_delete=models.CASCADE, related_name="mappings"
    )
    canonical_key = models.CharField(max_length=128)  # например: "Ҳудудлар номи"
    # список возможных заголовков/паттернов
    aliases = ArrayField(models.CharField(max_length=256), default=list)
    # опциональные правила
    dtype = models.CharField(
        max_length=16,
        choices=[("text", "text"), ("number", "number"), ("date", "date")],
        default="text",
    )
    required = models.BooleanField(default=False)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["template", "canonical_key"], name="uniq_template_canonical_key"
            )
        ]

    def __str__(self):
        return f"{self.template.name} :: {self.canonical_key}"


def excel_upload_to(instance, filename):
    # /media/uploads/2025-09-20/filename.xlsx
    d = datetime.now()
    return f"uploads/{d:%Y-%m-%d}/{filename}"


class Workbook(models.Model):
    STATUS_NEW = "new"
    STATUS_IMPORTING = "importing"
    STATUS_READY = "ready"
    STATUS_ERROR = "error"
    STATUS_CHOICES = [
        (STATUS_NEW, "new"),
        (STATUS_IMPORTING, "importing"),
        (STATUS_READY, "ready"),
        (STATUS_ERROR, "error"),
    ]

    file = models.FileField(upload_to=excel_upload_to, blank=True, null=True)
    filename = models.CharField(max_length=255)
    sha256 = models.CharField(max_length=64, db_index=True)
    uploaded_by = models.ForeignKey("auth.User", null=True, on_delete=models.SET_NULL)
    uploaded_at = models.DateTimeField(auto_now_add=True)
    status = models.CharField(max_length=32, default=STATUS_NEW, choices=STATUS_CHOICES)
    template = models.ForeignKey(
        "DataTemplate",
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name="workbooks",
        help_text="Фиксированный шаблон. Если не указан — сработает авто-детект (если он разрешён ниже)."
    )
    auto_template = models.BooleanField(
        default=True,
        help_text="Когда включено — импорт попытается авто-детектить шаблон по заголовкам."
    )
    sheets = models.CharField(
        max_length=128, blank=True, default="",
        help_text="Имя листа (пусто — первый лист книги)."
    )
    header_row = models.PositiveIntegerField(
        null=True, blank=True,
        help_text="Номер строки заголовка (1-based). Пусто/0 — авто."
    )

    class Meta:
        verbose_name = "Таблица"
        verbose_name_plural = "Таблицы"
        indexes = [
            models.Index(fields=["uploaded_at"]),
            models.Index(fields=["status"]),
        ]

    def __str__(self):
        return self.filename or (self.file.name if self.file else f"workbook#{self.pk}")


class ImportBatch(models.Model):
    workbook = models.ForeignKey(Workbook, on_delete=models.CASCADE)
    started_at = models.DateTimeField(auto_now_add=True)
    finished_at = models.DateTimeField(null=True, blank=True)
    status = models.CharField(max_length=32, default="running")
    meta = models.JSONField(default=dict, blank=True)


class Sheet(models.Model):
    workbook = models.ForeignKey(Workbook, on_delete=models.CASCADE)
    name = models.CharField(max_length=255)
    index = models.IntegerField()
    n_rows = models.IntegerField(default=0)
    n_cols = models.IntegerField(default=0)

    class Meta:
        indexes = [models.Index(fields=["workbook", "name"])]


class Cell(models.Model):
    sheet = models.ForeignKey(Sheet, on_delete=models.CASCADE)
    import_batch = models.ForeignKey(ImportBatch, on_delete=models.CASCADE)
    row_index = models.IntegerField()
    col_index = models.IntegerField()
    col_name = models.CharField(max_length=255, null=True, blank=True)
    addr = models.CharField(max_length=16)  # A1, B3...
    value_raw = models.TextField(null=True, blank=True)
    value_text = models.TextField(null=True, blank=True)
    value_num = models.DecimalField(max_digits=24, decimal_places=6, null=True, blank=True)
    value_dt = models.DateField(null=True, blank=True, db_index=True)
    dtype = models.CharField(max_length=16, default="text")
    kv_name = models.CharField(max_length=255, null=True, blank=True)
    kv_keys = models.JSONField(default=dict, blank=True)

    class Meta:
        indexes = [
            models.Index(fields=["sheet", "row_index"]),
            models.Index(fields=["sheet", "col_index"]),
        ]


class Dataset(models.Model):
    sheet = models.ForeignKey(Sheet, on_delete=models.CASCADE, related_name='datasets')
    name = models.CharField(max_length=255)
    inferred_schema = models.JSONField(default=dict, blank=True)
    primary_key = models.JSONField(default=dict, blank=True)
    meta = models.JSONField(default=dict, blank=True)
    period_date = models.DateField(null=True, blank=True, db_index=True)
    created_at = models.DateTimeField(null=True, blank=True)

    def __str__(self):
        return f"{self.name} (#{self.pk})"


class DatasetRow(models.Model):
    dataset = models.ForeignKey(Dataset, on_delete=models.CASCADE, related_name="rows")
    data = models.JSONField()
    imported_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [
            models.Index(fields=["dataset", "imported_at"]),
        ]

    def __str__(self):
        return f"row#{self.pk} / ds#{self.dataset_id}"
