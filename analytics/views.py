from django.db.models import CharField, F, Window, Q
from django.db.models.functions import Cast, RowNumber
from django.db.models import Count
from rest_framework import viewsets, filters, permissions
from django_filters.rest_framework import DjangoFilterBackend
from django.db.models.fields.json import KeyTextTransform
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from ingest.models import Dataset, DatasetRow, HandleRegistry, UploadHistory
from .serializers import DatasetSerializer, DatasetRowSerializer, HandleRegistrySerializer
from .views_resolve import format_client_date, parse_client_date


class HandleRegistryViewSet(viewsets.ReadOnlyModelViewSet):
    """
    /api/handles/ — список хэндлов для сайдбара/меню.
    Поддерживает:
      - фильтры: visible, group, handle
      - поиск: по handle/title
      - сортировка: order_index (по умолчанию), handle
      - mine=1 — только хэндлы текущего пользователя (по allowed_users)
      - include=users — добавить allowed_user_ids в выдачу
    """
    serializer_class = HandleRegistrySerializer
    permission_classes = [permissions.IsAuthenticated]
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = ["visible", "group", "handle"]
    search_fields = ["handle", "title"]
    ordering_fields = ["order_index", "handle", "id"]
    ordering = ["order_index", "handle"]

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
