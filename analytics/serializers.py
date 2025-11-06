from django.contrib.auth import get_user_model
from rest_framework import serializers
from egovuz_provider.models import UserProfile

from .models import ChartConfig, Dashboard
from ingest.models import Dataset, DatasetRow, HandleRegistry, Workbook
from .views_common import user_can_edit_handle
from .views_resolve import format_client_date

User = get_user_model()

class UserProfileSerializer(serializers.ModelSerializer):
    class Meta:
        model = UserProfile
        fields = [
            "egov_uid", "pin", "full_name", "first_name", "last_name",
            "middle_name", "last_sync"
        ]
        read_only_fields = ["last_sync"]

class UserSerializer(serializers.ModelSerializer):
    profile = UserProfileSerializer(required=False)
    is_superuser = serializers.BooleanField(required=False)
    is_staff = serializers.BooleanField(required=False)
    # для списка/деталей будет удобно видеть привязанные handles (только чтение)
    allowed_handles = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = [
            "id", "username", "email", "is_active",
            "is_superuser", "is_staff", "date_joined", "last_login",
            "profile", "allowed_handles",
        ]
        read_only_fields = ["date_joined", "last_login"]

    def get_allowed_handles(self, obj):
        qs = HandleRegistry.objects.filter(allowed_users=obj).order_by("handle")
        return [{"handle": h.handle, "title": h.title} for h in qs]

    def update(self, instance, validated):
        # вложенное обновление профиля
        prof_data = validated.pop("profile", None)
        user = super().update(instance, validated)
        if prof_data is not None:
            profile, _ = UserProfile.objects.get_or_create(user=user)
            for k, v in prof_data.items():
                setattr(profile, k, v)
            profile.save()
        return user

    def create(self, validated):
        prof_data = validated.pop("profile", None)
        # пароль на создание отдаём отдельным методом (set_password), здесь без него
        user = User.objects.create(**validated)
        UserProfile.objects.get_or_create(user=user)
        if prof_data:
            for k, v in prof_data.items():
                setattr(user.profile, k, v)
            user.profile.save()
        return user


class DatasetSerializer(serializers.ModelSerializer):
    fullname = serializers.CharField(source='sheet.workbook.filename', read_only=True)
    workbook_id = serializers.IntegerField(source='sheet.workbook_id', read_only=True)
    sheet_name = serializers.CharField(source='sheet.name', read_only=True)
    handle = serializers.CharField(source='sheet.workbook.handle', read_only=True)
    period_date = serializers.DateField(source='sheet.workbook.period_date', read_only=True, format="%d.%m.%Y")
    sheet_index = serializers.IntegerField(source='sheet.index', read_only=True)
    class Meta:
        model = Dataset
        fields = [
            "id", "name", "sheet_id", "inferred_schema", "meta", "handle", "period_date", "status", "version",
            "fullname", "workbook_id","sheet_name", "sheet_index",
        ]

class DatasetRowSerializer(serializers.ModelSerializer):
    class Meta:
        model = DatasetRow
        fields = ["id", "data", "imported_at"]


class HandleRegistrySerializer(serializers.ModelSerializer):
    periods = serializers.SerializerMethodField()
    periods_detailed = serializers.SerializerMethodField()
    editable = serializers.SerializerMethodField()
    can_upload = serializers.SerializerMethodField()
    fullname = serializers.SerializerMethodField()
    allowed_user_ids = serializers.SerializerMethodField()  # по запросу include=users

    class Meta:
        model = HandleRegistry
        fields = [
            "id",
            "handle",
            "title",
            "order_index",
            "group",
            "visible",
            "icon",
            "color",
            "style_json",
            # вычисляемые:
            "fullname",
            "periods",
            "editable",
            "can_upload",
            "allowed_user_ids",
            "periods_detailed",
        ]

    def get_fullname(self, obj: HandleRegistry):
        # Последнее "человеческое" имя файла из Workbook, иначе title/handle
        qs = (Workbook.objects
              .filter(handle=obj.handle)
              .values_list("filename", flat=True)
              .order_by("-period_date", "-id"))
        last = next((f for f in qs if f), None)
        return last or (obj.title or obj.handle)

    def get_periods(self, obj: HandleRegistry):
        """
        Возвращает список дат-периодов с учётом фильтра статуса (?status=approved|draft|all).
        По умолчанию — только approved (как и в periods_detailed).
        """
        req = self.context.get("request")
        status_filter = (req.query_params.get("status") or "approved").lower() if req else "approved"
        if status_filter not in ("approved", "draft", "all"):
            status_filter = "approved"

        # Базовый список всех воркбуков по handle в порядке убывания даты
        wbs = (Workbook.objects
               .filter(handle=obj.handle)
               .order_by("-period_date", "-id"))

        # Если all — оставляем прежнее поведение (все даты)
        if status_filter == "all":
            return [format_client_date(d) for d in wbs.values_list("period_date", flat=True) if d]

        # Иначе — включаем дату только если для этого воркбука есть датасет с нужным статусом
        periods = []
        for wb in wbs:
            ds_exists = Dataset.objects.filter(sheet__workbook=wb, status=(
                Dataset.STATUS_APPROVED if status_filter == "approved" else Dataset.STATUS_DRAFT
            )).exists()
            if ds_exists and wb.period_date:
                periods.append(format_client_date(wb.period_date))
        return periods

    def get_editable(self, obj: HandleRegistry):
        req = self.context.get("request")
        return user_can_edit_handle(req.user, obj.handle) if req else False

    def get_can_upload(self, obj: HandleRegistry):
        # Пока логика совпадает с editable
        return self.get_editable(obj)

    def get_periods_detailed(self, obj: HandleRegistry):
        req = self.context.get("request")
        include = (req.query_params.get("include") or "").split(",") if req else []
        if "periods_detailed" not in [s.strip() for s in include]:
            return None

        # NEW: фильтр статуса из query (?status=approved|draft|all), по умолчанию approved
        status_filter = (req.query_params.get("status") or "approved").lower() if req else "approved"
        if status_filter not in ("approved", "draft", "all"):
            status_filter = "approved"

        items = []
        wbs = Workbook.objects.filter(handle=obj.handle).order_by("-period_date", "-id")
        for wb in wbs:
            ds_qs = Dataset.objects.filter(sheet__workbook=wb).order_by("-created_at", "-id")
            if status_filter == "approved":
                ds = ds_qs.filter(status=Dataset.STATUS_APPROVED).first()
            elif status_filter == "draft":
                ds = ds_qs.filter(status=Dataset.STATUS_DRAFT).first()
            else:
                ds = ds_qs.first()

            # если требуется фильтрация по конкретному статусу и датасета нет — пропускаем
            if status_filter in ("approved", "draft") and ds is None:
                continue

            items.append({
                "period_date": format_client_date(wb.period_date),
                "dataset_id": ds.id if ds else None,
                "status": ds.status if ds else None,
                "version": ds.version if ds else None,
            })
        return items

    def get_allowed_user_ids(self, obj: HandleRegistry):
        """
        Только если ?include=users — иначе возвращаем None (и DRF не положит поле).
        Это удобно, чтобы не тянуть M2M всегда.
        """
        req = self.context.get("request")
        include = (req.query_params.get("include") or "").split(",") if req else []
        if "users" not in [s.strip() for s in include]:
            return None
        return list(obj.allowed_users.values_list("username", flat=True))
