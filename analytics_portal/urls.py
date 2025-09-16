"""
URL configuration for analytics_portal project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/5.2/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""
from django.contrib import admin
from django.http import JsonResponse
from django.urls import path, include
from django.views.generic import RedirectView, TemplateView
from django.conf.urls.static import static
from django.views.decorators.csrf import ensure_csrf_cookie
from django.views.decorators.http import require_GET
from django.middleware.csrf import get_token

from django.conf import settings
from web_project.views import SystemView

admin.site.site_header = 'Реестр паспортов'
admin.site.site_title = 'Реестр паспортов'

@require_GET
@ensure_csrf_cookie
def csrf_view(request):
    """
    Возвращает детальную информацию для фронта:
    - сам CSRF-токен (чтобы не читать cookie во фронте),
    - имя cookie и заголовка, флаги безопасности,
    - краткую информацию о сессии/пользователе.
    """
    token = get_token(request)  # генерирует/возвращает токен и синхронизирован с установленной csrftoken-cookie

    return JsonResponse({
        "detail": "ok",
        "csrf": {
            "token": token,  # можно сразу ставить в X-CSRFToken на фронте
            "cookieName": getattr(settings, "CSRF_COOKIE_NAME", "csrftoken"),
            "headerName": "X-CSRFToken",
            "path": getattr(settings, "CSRF_COOKIE_PATH", "/"),
            "secure": bool(getattr(settings, "CSRF_COOKIE_SECURE", False)),
            "httpOnly": False,  # CSRF-cookie по умолчанию НЕ HttpOnly (так фронт может прочитать при необходимости)
            "sameSite": getattr(settings, "CSRF_COOKIE_SAMESITE", "Lax"),
            "trustedOrigins": list(getattr(settings, "CSRF_TRUSTED_ORIGINS", [])),
        },
        "session": {
            "authenticated": request.user.is_authenticated,
            "user": (
                {
                    "id": request.user.id,
                    "email": getattr(request.user, "email", None),
                    "username": getattr(request.user, "username", None),
                } if request.user.is_authenticated else None
            )
        }
    })

urlpatterns = [
    path('admin/', admin.site.urls),
    path('accounts/', include('allauth.urls')),
    path("api/auth/", include("dj_rest_auth.urls")), # JSON: /login/ /logout/ /user/ /password/reset/
    path("api/auth/csrf/", csrf_view), # точка, чтобы фронт получил csrftoken cookie
    path('api/', include('analytics.urls')),
    path('', RedirectView.as_view(pattern_name='dashboard-page', permanent=False)),
] + static(settings.STATIC_URL, document_root=settings.STATIC_ROOT) \
  + static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
