# analytics/views_users.py
from django.contrib.auth import get_user_model
from django.db import transaction
from rest_framework import viewsets, permissions, status
from rest_framework.decorators import action
from rest_framework.response import Response
from ingest.models import HandleRegistry
from .serializers import UserSerializer

User = get_user_model()

class IsSuperAdminOrGroup(permissions.BasePermission):
    """
    Разрешаем доступ суперпользователям или пользователям из группы 'superadmins'.
    """
    def has_permission(self, request, view):
        u = request.user
        return bool(u and u.is_authenticated and (u.is_superuser or u.groups.filter(name="superadmins").exists()))

class UserViewSet(viewsets.ModelViewSet):
    """
    /api/users/ — CRUD пользователей.
    Доступ: только суперпользователь или группа 'superadmins'.
    """
    queryset = User.objects.all().order_by("-date_joined")
    serializer_class = UserSerializer
    permission_classes = [IsSuperAdminOrGroup]

    def get_queryset(self):
        qs = super().get_queryset()
        q = self.request.query_params.get("q")
        if q:
            qs = qs.filter(username__icontains=q) | qs.filter(email__icontains=q)
        return qs

    def perform_destroy(self, instance):
        # защитимся от удаления самого себя и последнего суперпользователя
        if instance == self.request.user:
            return
        if instance.is_superuser and User.objects.filter(is_superuser=True).exclude(pk=instance.pk).count() == 0:
            return
        return super().perform_destroy(instance)

    @action(detail=True, methods=["post"])
    def set_password(self, request, pk=None):
        """
        POST /api/users/{id}/set_password/
        body: {"new_password": "..."}
        """
        user = self.get_object()
        new_password = (request.data.get("new_password") or "").strip()
        if not new_password:
            return Response({"detail": "new_password required"}, status=400)
        if user == request.user and not request.user.is_superuser:
            # можно запретить менять себе пароль этим методом, при желании
            pass
        user.set_password(new_password)
        user.save(update_fields=["password"])
        return Response({"detail": "password updated"})

    @action(detail=True, methods=["put", "post"])
    @transaction.atomic
    def set_allowed_handles(self, request, pk=None):
        """
        PUT/POST /api/users/{id}/set_allowed_handles/
        body: {"handles": ["1-eksport", "2-import", ...]}
        """
        user = self.get_object()
        handles = request.data.get("handles") or []
        if not isinstance(handles, (list, tuple)):
            return Response({"detail": "handles must be list"}, status=400)

        # сбросим текущие связи и установим новые
        HandleRegistry.objects.filter(allowed_users=user).update()
        # для производительности — пройдёмся по существующим
        existing = {h.handle: h for h in HandleRegistry.objects.filter(handle__in=handles)}
        # сначала почистим всех
        for h in HandleRegistry.objects.filter(allowed_users=user):
            h.allowed_users.remove(user)
        # затем добавим заново из входного списка
        for slug in handles:
            h = existing.get(slug) or HandleRegistry.objects.filter(handle=slug).first()
            if h:
                h.allowed_users.add(user)

        return Response({"detail": "allowed handles updated"})

    @action(detail=True, methods=["post"])
    def activate(self, request, pk=None):
        user = self.get_object()
        user.is_active = True
        user.save(update_fields=["is_active"])
        return Response({"detail": "activated"})

    @action(detail=True, methods=["post"])
    def deactivate(self, request, pk=None):
        user = self.get_object()
        # не блокируем себя случайно
        if user == request.user:
            return Response({"detail": "cannot deactivate yourself"}, status=400)
        user.is_active = False
        user.save(update_fields=["is_active"])
        return Response({"detail": "deactivated"})
