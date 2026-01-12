# analytics_portal/middleware.py
from datetime import timedelta

class PerUserSessionExpiryMiddleware:
    """
    Для всех: 30 минут (берётся из SESSION_COOKIE_AGE)
    Для группы long_session: более длинная сессия.
    """
    LONG_SESSION_SECONDS = 14 * 24 * 60 * 60

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        user = getattr(request, "user", None)
        if user and user.is_authenticated:
            if user.groups.filter(name="long_session").exists():
                try:
                    request.session.set_expiry(self.LONG_SESSION_SECONDS)
                except Exception:
                    pass

        return self.get_response(request)
