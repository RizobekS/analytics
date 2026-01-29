# analytics/permissions.py
from rest_framework.permissions import BasePermission
from django.conf import settings

class IsAuthenticatedOrApiKey(BasePermission):
    """
    Доступ:
    - либо залогиненный пользователь
    - либо валидный X-API-KEY
    """

    def has_permission(self, request, view):
        # обычная аутентификация
        if request.user and request.user.is_authenticated:
            return True

        # API key
        expected = getattr(settings, "EXTERNAL_EKSPORT_API_KEY", "")
        if not expected:
            return False

        provided = request.headers.get("X-API-KEY")
        return provided == expected
