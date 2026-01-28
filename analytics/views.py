from django.db.models import CharField, F, Window, Q
from django.db.models.functions import Cast, RowNumber
from django.db.models import Count
from rest_framework import viewsets, filters, permissions, status
from django_filters.rest_framework import DjangoFilterBackend
from django.db.models.fields.json import KeyTextTransform
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated, IsAdminUser
from rest_framework.response import Response
from rest_framework.views import APIView

from ingest.models import Dataset, DatasetRow, HandleRegistry, UploadHistory
from .serializers import DatasetSerializer, DatasetRowSerializer, HandleRegistrySerializer
from .views_resolve import format_client_date, parse_client_date


class HandleRegistryViewSet(viewsets.ModelViewSet):
    """
    /api/handles/ — список хэндлов для сайдбара/меню.
    Поддерживает:
      - фильтры: visible, group, handle
      - поиск: по handle/title
      - сортировка: order_index (по умолчанию), handle
      - mine=1 — только хэндлы текущего пользователя (по allowed_users)
      - include=users — добавить allowed_user_ids в выдачу

    POST /api/handles/register/ - регистрация handle (staff only)
    """
    serializer_class = HandleRegistrySerializer
    permission_classes = [permissions.IsAuthenticated]
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = ["visible", "group", "handle", "table_kind"]
    search_fields = ["handle", "title"]
    ordering_fields = ["order_index", "handle", "id"]
    ordering = ["order_index", "handle"]

    def get_permissions(self):
        # чтение - всем залогиненным
        if self.action in ("list", "retrieve"):
            return [IsAuthenticated()]
        # регистрация/изменения - только админам
        return [IsAuthenticated(), IsAdminUser()]

    @action(detail=False, methods=["post"], url_path="register")
    def register(self, request):
        """
        payload:
        {
          "handle": "my_handle",
          "title": "Моя таблица",
          "group": "grp1",
          "visible": true,
          "table_kind": "legacy|v2",
          "order_index": 1000
        }
        """
        handle = (request.data.get("handle") or "").strip()
        if not handle:
            return Response({"detail": "handle is required"}, status=status.HTTP_400_BAD_REQUEST)

        defaults = {
            "title": (request.data.get("title") or "").strip(),
            "group": (request.data.get("group") or "").strip(),
            "visible": bool(request.data.get("visible", True)),
            "table_kind": (request.data.get("table_kind") or "legacy"),
        }
        if request.data.get("order_index") is not None:
            try:
                defaults["order_index"] = int(request.data.get("order_index"))
            except Exception:
                return Response({"detail": "order_index must be integer"}, status=status.HTTP_400_BAD_REQUEST)

        obj, created = HandleRegistry.objects.get_or_create(handle=handle, defaults=defaults)

        # если уже существует — обновим переданные поля (чтобы фронт мог “донастроить”)
        if not created:
            changed = False
            for k, v in defaults.items():
                if v != "" and getattr(obj, k) != v:
                    setattr(obj, k, v)
                    changed = True
            if changed:
                obj.save()

        # бонус: добавим создателя в allowed_users, чтобы он мог загружать таблицы
        try:
            obj.allowed_users.add(request.user)
        except Exception:
            pass

        ser = self.get_serializer(obj)
        return Response(
            {"created": created, "handle": ser.data},
            status=status.HTTP_201_CREATED if created else status.HTTP_200_OK
        )

    def get_queryset(self):
        qs = HandleRegistry.objects.all()
        # видимость можно оставить как есть; фронт и так передаёт visible=true
        # mine=1 — оставить только назначенные пользователю записи
        mine = (self.request.query_params.get("mine") or "").lower() in ("1", "true", "yes")
        if mine and not self.request.user.is_superuser:
            qs = qs.filter(allowed_users=self.request.user)
        return qs


class UploadHistoryView(APIView):
    """
    GET /api/upload-history/?handle=...&user_id=...&date_from=DD.MM.YYYY&date_to=DD.MM.YYYY&limit=100&offset=0
    - staff/superuser видит всё
    - обычный пользователь видит только свои события
    """
    permission_classes = [IsAuthenticated]

    def get(self, request):
        qs = UploadHistory.objects.all().order_by("-created_at")
        handle = (request.query_params.get("handle") or "").strip()
        user_id = request.query_params.get("user_id")
        date_from = parse_client_date(request.query_params.get("date_from"))
        date_to   = parse_client_date(request.query_params.get("date_to"))

        if handle:
            qs = qs.filter(handle=handle)
        if user_id:
            qs = qs.filter(user_id=user_id)

        if date_from:
            qs = qs.filter(created_at__date__gte=date_from)
        if date_to:
            qs = qs.filter(created_at__date__lte=date_to)

        # если не админ — только свои
        if not (request.user.is_staff or request.user.is_superuser):
            qs = qs.filter(user=request.user)

        try:
            limit  = max(1, min(500, int(request.query_params.get("limit") or 100)))
            offset = max(0, int(request.query_params.get("offset") or 0))
        except ValueError:
            limit, offset = 100, 0

        items = []
        for h in qs[offset:offset+limit]:
            items.append({
                "id": h.id,
                "created_at": h.created_at.isoformat(),
                "user_id": h.user_id,
                "user": getattr(h.user, "username", None),
                "handle": h.handle,
                "period_date": format_client_date(h.period_date),
                "workbook_id": h.workbook_id,
                "dataset_id": h.dataset_id,
                "filename": h.filename,
                "rows_count": h.rows_count,
                "action": h.action,
                "status_before": h.status_before,
                "status_after": h.status_after,
                "extra": h.extra,
            })
        return Response({"results": items})
