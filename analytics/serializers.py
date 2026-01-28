from allauth.account.models import EmailAddress
from dj_rest_auth.serializers import UserDetailsSerializer
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
    # доп. поля для удобства создания
    password = serializers.CharField(write_only=True, required=False, allow_blank=True)
    email_verified = serializers.BooleanField(write_only=True, required=False, default=False)
    groups = serializers.ListField(
        child=serializers.CharField(), required=False, write_only=True, help_text="['superadmins', ...]"
    )
    handles = serializers.ListField(
        child=serializers.CharField(), required=False, write_only=True, help_text="['1-eksport', ...]"
    )

    # только чтение — чтобы фронт видел свои доступы
    allowed_handles = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = [
            "id", "username", "email", "is_active",
            "is_superuser", "is_staff", "date_joined", "last_login",
            "profile", "allowed_handles",
            # write-only:
            "password", "email_verified", "groups", "handles",
        ]
        read_only_fields = ["date_joined", "last_login"]

    def get_allowed_handles(self, obj):
        qs = HandleRegistry.objects.filter(allowed_users=obj).order_by("handle")
        return [{"handle": h.handle, "title": h.title} for h in qs]

    def _ensure_username_email(self, data: dict) -> dict:
        """
        Если фронт прислал только email — используем его как username.
        Если прислал оба — оставляем как есть.
        """
        email = (data.get("email") or "").strip()
        username = (data.get("username") or "").strip()
        if email and not username:
            data["username"] = email
        return data

    def _apply_groups(self, user: User, groups_list):
        if not groups_list:
            return
        from django.contrib.auth.models import Group
        qs = Group.objects.filter(name__in=groups_list)
        user.groups.set(qs)

    def _apply_handles(self, user: User, handles_list):
        if not handles_list:
            return
        for h in HandleRegistry.objects.filter(handle__in=handles_list):
            h.allowed_users.add(user)

    def _ensure_email_address(self, user: User, email: str, verified: bool):
        """
        Создаём/обновляем allauth EmailAddress, чтобы allauth знал почту.
        """
        if not email:
            return
        ea, _ = EmailAddress.objects.get_or_create(user=user, email=email)
        # если хотим сразу верифицировать корпоративную почту — ставим verified=True
        if verified and not ea.verified:
            ea.verified = True
            ea.primary = True
            ea.save()

    def create(self, validated):
        prof_data = validated.pop("profile", None)
        raw_password = validated.pop("password", "") or ""
        email_verified = bool(validated.pop("email_verified", False))
        groups_list = validated.pop("groups", None)
        handles_list = validated.pop("handles", None)

        validated = self._ensure_username_email(validated)

        # создаём пользователя
        user = User.objects.create(
            username=validated.get("username"),
            email=validated.get("email"),
            is_active=validated.get("is_active", True),
            is_staff=validated.get("is_staff", False),
            is_superuser=validated.get("is_superuser", False),
        )
        if raw_password:
            user.set_password(raw_password)
        else:
            # можно оставить пустым (потом установить), либо задать unusable
            user.set_unusable_password()
        user.save()

        # профиль OneID (PIN/egov_uid/ФИО)
        profile, _ = UserProfile.objects.get_or_create(user=user)
        if prof_data:
            for k, v in prof_data.items():
                setattr(profile, k, v)
            profile.save()

        # группы / доступы к хэндлам
        self._apply_groups(user, groups_list)
        self._apply_handles(user, handles_list)

        # allauth EmailAddress
        self._ensure_email_address(user, user.email, email_verified)

        return user

    def update(self, instance, validated):
        prof_data = validated.pop("profile", None)
        raw_password = validated.pop("password", "") or ""
        email_verified = bool(validated.pop("email_verified", False))
        groups_list = validated.pop("groups", None)
        handles_list = validated.pop("handles", None)

        validated = self._ensure_username_email(validated)

        # базовые поля
        for f in ("username", "email", "is_active", "is_staff", "is_superuser"):
            if f in validated:
                setattr(instance, f, validated[f])

        if raw_password:
            instance.set_password(raw_password)

        instance.save()

        # профиль
        profile, _ = UserProfile.objects.get_or_create(user=instance)
        if prof_data:
            for k, v in prof_data.items():
                setattr(profile, k, v)
            profile.save()

        # группы/хэндлы (сетово)
        if groups_list is not None:
            self._apply_groups(instance, groups_list)
        if handles_list is not None:
            # очистим старые и поставим новые
            for h in HandleRegistry.objects.filter(allowed_users=instance):
                h.allowed_users.remove(instance)
            self._apply_handles(instance, handles_list)

        # email address allauth
        self._ensure_email_address(instance, instance.email, email_verified)

        return instance


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
            "table_kind",
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


class CurrentUserSerializer(UserDetailsSerializer):
    # эти два — чтобы фронт знал “статус” пользователя
    is_superuser = serializers.BooleanField(read_only=True)
    is_staff = serializers.BooleanField(read_only=True)

    # группы и (опционально) пермишены
    groups = serializers.SerializerMethodField()
    permissions = serializers.SerializerMethodField()

    # удобно отдать связанную карточку профиля OneID
    profile = UserProfileSerializer(read_only=True)

    # и что этот пользователь может редактировать (по твоей логике доступа)
    allowed_handles = serializers.SerializerMethodField()

    class Meta(UserDetailsSerializer.Meta):
        model = User
        fields = (
            "pk", "username", "email", "first_name", "last_name",
            "is_superuser", "is_staff",
            "groups", "permissions",
            "profile", "allowed_handles",
        )

    def get_groups(self, obj):
        return list(obj.groups.values_list("name", flat=True))

    def get_permissions(self, obj):
        # при желании можно убрать, если не нужно
        return list(obj.user_permissions.values_list("codename", flat=True))

    def get_allowed_handles(self, obj):
        # obj — текущий User
        qs = HandleRegistry.objects.filter(allowed_users=obj).order_by("handle")

        # Если контекст у сериализатора есть — используем его,
        # иначе подстрахуемся и считаем права напрямую от obj.
        req = self.context.get("request") if hasattr(self, "context") else None
        is_super = bool(getattr(obj, "is_superuser", False))

        items = []
        for h in qs:
            if is_super:
                can_edit = True
            else:
                # без request: проверяем M2M напрямую
                can_edit = h.allowed_users.filter(id=obj.id).exists()

            items.append({
                "handle": h.handle,
                "title": h.title,
                "editable": can_edit,
                "can_upload": can_edit,  # сейчас одинаково; позже разведём логику
            })
        return items
