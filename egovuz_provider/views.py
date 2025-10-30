import requests
from urllib.parse import urlencode

from allauth.socialaccount.providers.oauth2.client import OAuth2Client
from allauth.socialaccount.providers.oauth2.views import (
    OAuth2Adapter, OAuth2LoginView, OAuth2CallbackView
)

AUTH_BASE = "https://sso.egov.uz/sso/oauth/Authorization.do"

class EgovUzOAuth2Client(OAuth2Client):
    """
    Кастомный клиент: нестандартные имена параметров:
    - response_type=one_code
    - grant_type=one_authorization_code
    - профиль: grant_type=one_access_token_identify
    """
    def get_access_token(self, code):
        data = {
            "grant_type": "one_authorization_code",
            "client_id": self.consumer_key,
            "client_secret": self.consumer_secret,
            "code": code,
            "redirect_uri": self.callback_url,
        }
        resp = requests.post(AUTH_BASE, data=data, timeout=15)
        resp.raise_for_status()
        return resp.json()

class EgovUzOAuth2Adapter(OAuth2Adapter):
    provider_id = "egovuz"
    access_token_url = AUTH_BASE
    authorize_url = AUTH_BASE
    profile_url = AUTH_BASE
    client_class = EgovUzOAuth2Client

    def complete_login(self, request, app, token, **kwargs):
        """
        Запрашиваем профиль:
        grant_type=one_access_token_identify + client_id/secret + access_token + scope
        """
        scope = app.settings.get("SCOPE") or app.client_id  # если scope не задан — пусть совпадает с app
        payload = {
            "grant_type": "one_access_token_identify",
            "client_id": app.client_id,
            "client_secret": app.secret,
            "access_token": token.token,
            "scope": scope,
        }
        resp = requests.post(self.profile_url, data=payload, timeout=15)
        resp.raise_for_status()
        extra_data = resp.json()
        # Вернём SocialLogin с extra_data
        return self.get_provider().sociallogin_from_response(request, extra_data)

    def get_authorization_url(self, request, app):
        """
        Собираем URL с их нестандартным response_type=one_code
        """
        params = {
            "response_type": "one_code",
            "client_id": app.client_id,
            "redirect_uri": self.get_callback_url(request, app),
            "scope": app.settings.get("SCOPE") or app.client_id,
            "state": self.state_from_request(request),
        }
        return f"{self.authorize_url}?{urlencode(params)}"

oauth2_login    = OAuth2LoginView.adapter_view(EgovUzOAuth2Adapter)
oauth2_callback = OAuth2CallbackView.adapter_view(EgovUzOAuth2Adapter)
