# egovuz_provider/views.py
import secrets
from django.urls import reverse
from django.contrib.sites.models import Site
from django.contrib.auth import login as auth_login
from django.contrib.auth import get_user_model
from allauth.socialaccount.models import SocialApp
import requests
from urllib.parse import urlencode
from django.conf import settings
from django.http import HttpResponseBadRequest, HttpResponseRedirect, JsonResponse

from allauth.socialaccount.models import SocialToken
from allauth.socialaccount.providers.oauth2.client import OAuth2Client
from allauth.socialaccount.providers.oauth2.views import (
    OAuth2Adapter, OAuth2CallbackView
)
from allauth.socialaccount.helpers import complete_social_login
from allauth.utils import get_request_param
from django.db.models import Q
from .models import UserProfile

User = get_user_model()

# Разделённые URL'ы
BROKER_AUTHORIZE_URL = getattr(settings, "EGOV_BROKER_AUTHORIZE_URL", "https://sso.miit.uz/one-id/authorize")
ONEID_TOKEN_URL      = "https://sso.egov.uz/sso/oauth/Authorization.do"
ONEID_PROFILE_URL    = ONEID_TOKEN_URL
BROKER_REDIRECT_URL  = getattr(settings, "EGOV_BROKER_REDIRECT_URL", None)


def _get_app(request):
    # Получаем SocialApp(provider='egovuz') для текущего SITE_ID
    site_id = getattr(settings, "SITE_ID", None)
    if site_id:
        site = Site.objects.get(pk=site_id)
        return SocialApp.objects.get(provider="egovuz", sites=site)
    # fallback — если по SITE_ID не нашли (на dev/ngrok)
    return SocialApp.objects.filter(provider="egovuz").first()

# egovuz_provider/views.py

class EgovUzOAuth2Client(OAuth2Client):
    def get_access_token(self, code):
        data = {
            "grant_type": "one_authorization_code",
            "client_id": self.consumer_key,
            "client_secret": self.consumer_secret,
            "code": code,
            # ДОЛЖЕН совпадать с redirect_uri, который брокер использовал у OneID:
            "redirect_uri": getattr(settings, "ONE_ID_REDIRECT_URL"),
        }
        resp = requests.post(ONEID_TOKEN_URL, data=data, timeout=15)
        if not resp.ok:
            # покажем тело ответа — сильно упрощает отладку
            return HttpResponseBadRequest(f"OneID token error {resp.status_code}: {resp.text}")
        try:
            return resp.json()
        except ValueError:
            return HttpResponseBadRequest(f"OneID token non-JSON response: {resp.text[:500]}")


class EgovUzOAuth2Adapter(OAuth2Adapter):
    provider_id = "egovuz"
    access_token_url = ONEID_TOKEN_URL
    authorize_url = BROKER_AUTHORIZE_URL
    profile_url = ONEID_PROFILE_URL
    client_class = EgovUzOAuth2Client

    def complete_login(self, request, app, token, **kwargs):
        scope = app.settings.get("SCOPE") or app.client_id
        payload = {
            "grant_type": "one_access_token_identify",
            "client_id": app.client_id,
            "client_secret": app.secret,
            "access_token": token.token,
            "scope": scope,
        }
        resp = requests.post(ONEID_PROFILE_URL, data=payload, timeout=15)
        resp.raise_for_status()
        extra_data = resp.json()
        return self.get_provider().sociallogin_from_response(request, extra_data)

def broker_login(request):
    state = secrets.token_urlsafe(16)
    request.session["egov_state"] = state

    callback = BROKER_REDIRECT_URL or request.build_absolute_uri(
        reverse("egovuz_callback")  # это "accounts/egovuz/callback/"
    )

    params = {"redirect_url": callback, "state": state}
    url = f"{BROKER_AUTHORIZE_URL}?{urlencode(params)}"
    return HttpResponseRedirect(url)

# КАСТОМНЫЙ CALLBACK
class EgovUzCallbackBrokerView(OAuth2CallbackView):
    def dispatch(self, request, *args, **kwargs):
        err = get_request_param(request, getattr(settings, "EGOV_BROKER_ERROR_PARAM", "error"))
        if err:
            return HttpResponseBadRequest(f"Broker error: {err}")

        code = get_request_param(request, "code")
        state = get_request_param(request, "state")

        adapter = self.adapter
        app = _get_app(request)
        if app is None:
            return HttpResponseBadRequest("SocialApp(egovuz) not configured")

        # Проверка state
        sess_state = request.session.get("egov_state")
        if state and sess_state and state != sess_state:
            return HttpResponseBadRequest("Invalid state")

        if not code:
            return HttpResponseBadRequest("Missing code param")

        # === Обмен кода на access_token ===
        client = adapter.get_client(request, app)
        token_data = client.get_access_token(code)
        if not isinstance(token_data, dict):
            return token_data

        access_token = token_data.get("access_token") or token_data.get("token") or token_data.get("accessToken")
        if not access_token:
            return HttpResponseBadRequest(f"No access_token in token response: {token_data}")

        token = SocialToken(token=access_token, app=app)

        # === Запрашиваем профиль сотрудника ===
        payload = {
            "grant_type": "one_access_token_identify",
            "client_id": app.client_id,
            "client_secret": app.secret,
            "access_token": access_token,
        }
        resp = requests.post(ONEID_PROFILE_URL, data=payload, timeout=15)
        if not resp.ok:
            return HttpResponseBadRequest(f"Profile request failed {resp.status_code}: {resp.text}")

        data = resp.json()
        egov_uid = data.get("pin") or data.get("user_id")
        uid = (str(egov_uid) if egov_uid is not None else "").strip()
        profile = (
            UserProfile.objects.select_related("user")
            .filter(Q(egov_uid__iexact=uid) | Q(pin__iexact=uid))
            .first()
        )
        if not profile:
            # Диагностика: вернём что реально пришло, чтобы сразу увидеть различия
            return JsonResponse(
                {
                    "status": "no_match",
                    "reason": "user not registered in local DB",
                    "received_uid": uid,
                    "raw_profile": data,  # что дал OneID (без секретов)
                },
                status=403,
            )
        pin = (data.get("pin") or "").strip()
        user = profile.user

        # === Логиним пользователя через сессию Django ===
        auth_login(request, user, backend="django.contrib.auth.backends.ModelBackend")

        # === Сохраняем или обновляем профиль ===
        if pin:
            profile.pin = pin
        profile.full_name = data.get("full_name") or profile.full_name
        profile.first_name = data.get("first_name") or profile.first_name
        profile.last_name = data.get("sur_name") or profile.last_name
        profile.middle_name = data.get("mid_name") or profile.middle_name
        profile.egov_uid = data.get("uid") or profile.pin
        profile.save()

        return JsonResponse({
            "status": "success",
            "username": user.username,
            "full_name": profile.full_name,
            "pin": profile.pin,
            "egov_uid": profile.egov_uid,
        })

oauth2_callback_broker = EgovUzCallbackBrokerView.adapter_view(EgovUzOAuth2Adapter)

