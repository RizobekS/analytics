# ingest/models.py
from django.conf import settings
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
    min_value = models.DecimalField(max_digits=24, decimal_places=6, null=True, blank=True)
    max_value = models.DecimalField(max_digits=24, decimal_places=6, null=True, blank=True)
    regex = models.CharField(max_length=256, blank=True, default="")
    choices = ArrayField(models.CharField(max_length=256), default=list, blank=True)

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


class HandleRegistry(models.Model):
    allowed_users = models.ManyToManyField(settings.AUTH_USER_MODEL, blank=True, related_name="allowed_handles")
    handle = models.SlugField(max_length=64, unique=True, db_index=True)
    title = models.CharField(max_length=255, blank=True, default="")
    order_index = models.IntegerField(default=1000, db_index=True)  # порядок карточек
    group = models.CharField(max_length=64, blank=True, default="")
    visible = models.BooleanField(default=True)
    icon = models.CharField(max_length=64, blank=True, default="")
    color = models.CharField(max_length=32, blank=True, default="")
    # на будущее: хранить стили Luckysheet/оформление
    style_json = models.JSONField(default=dict, blank=True)

    class Meta:
        ordering = ["order_index", "handle"]


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
    # NEW: стабильный логический идентификатор (для резолвера с фронта)
    handle = models.SlugField(max_length=64, null=True, blank=True, db_index=True)
    period_date = models.DateField(null=True, blank=True, db_index=True)

    def __str__(self):
        return f"{getattr(self, 'filename', 'Workbook')} #{self.pk} [{self.handle or '-'}]"

    class Meta:
        verbose_name = "Таблица"
        verbose_name_plural = "Таблицы"
        indexes = [
            models.Index(fields=["uploaded_at"]),
            models.Index(fields=["status"]),
            models.Index(fields=["handle"]),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=["handle", "period_date"],
                name="uniq_workbook_handle_period"
            )
        ]


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
    created_at = models.DateTimeField(auto_now_add=True, null=True, blank=True)
    # NEW: публикация датасета и его версия (для аналитики/аудита)
    STATUS_DRAFT = "draft"
    STATUS_APPROVED = "approved"
    STATUS_CHOICES = [(STATUS_DRAFT, "draft"), (STATUS_APPROVED, "approved")]
    status = models.CharField(max_length=16, choices=STATUS_CHOICES, default=STATUS_APPROVED, db_index=True)
    version = models.PositiveIntegerField(default=1, db_index=True)

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


# NEW: аудит строк с оптимистической блокировкой
class DatasetRowRevision(models.Model):
    row = models.ForeignKey(DatasetRow, on_delete=models.CASCADE, related_name='revisions')
    version = models.PositiveIntegerField()  # номер ревизии строки
    data_before = models.JSONField()
    data_after = models.JSONField()
    changed_by = models.ForeignKey("auth.User", null=True, on_delete=models.SET_NULL)
    changed_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = [("row", "version")]
        indexes = [
            models.Index(fields=["row", "version"]),
            models.Index(fields=["changed_at"]),
        ]


class UploadHistory(models.Model):
    ACTION_UPLOAD = "upload"
    ACTION_TRUNCATE_UPLOAD = "truncate_upload"
    ACTION_STATUS_CHANGE = "status_change"

    ACTION_CHOICES = [
        (ACTION_UPLOAD, "upload"),
        (ACTION_TRUNCATE_UPLOAD, "truncate_upload"),
        (ACTION_STATUS_CHANGE, "status_change"),
    ]

    user = models.ForeignKey("auth.User", null=True, on_delete=models.SET_NULL, related_name="upload_events")
    handle = models.SlugField(max_length=64, db_index=True)
    period_date = models.DateField(null=True, blank=True, db_index=True)

    workbook = models.ForeignKey(Workbook, null=True, blank=True, on_delete=models.SET_NULL)
    dataset = models.ForeignKey(Dataset,  null=True, blank=True, on_delete=models.SET_NULL)

    filename = models.CharField(max_length=255, blank=True, default="")
    rows_count = models.PositiveIntegerField(default=0)

    action = models.CharField(max_length=32, choices=ACTION_CHOICES)
    status_before = models.CharField(max_length=16, blank=True, default="")
    status_after  = models.CharField(max_length=16, blank=True, default="")

    extra = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        indexes = [
            models.Index(fields=["handle", "period_date", "created_at"]),
            models.Index(fields=["action", "created_at"]),
        ]

    def __str__(self):
        return f"[{self.created_at:%Y-%m-%d %H:%M}] {self.user_id} {self.action} {self.handle} {self.period_date}"
