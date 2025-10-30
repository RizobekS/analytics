from allauth.socialaccount.providers.base import ProviderAccount
from allauth.socialaccount.providers.oauth2.provider import OAuth2Provider
from allauth.socialaccount import app_settings
from allauth.socialaccount.providers import registry
from .views import EgovUzOAuth2Adapter

class EgovUzAccount(ProviderAccount):
    def to_str(self):
        d = self.account.extra_data or {}
        return d.get("full_name") or d.get("user_id") or super().to_str()

class EgovUzProvider(OAuth2Provider):
    id = "egovuz"                     # {% provider_login_url 'egovuz' %}
    name = "ID.Egov.UZ"
    account_class = EgovUzAccount

    oauth2_adapter_class = EgovUzOAuth2Adapter

    def extract_uid(self, data):
        # Единственный гарантированный идентификатор
        return str(data.get("user_id") or data.get("pin"))

    def extract_common_fields(self, data):
        # email может не прийти — оставляем пустым
        first_name = data.get("first_name") or ""
        last_name  = data.get("sur_name") or ""
        # user_id = "login" в их терминах
        username   = data.get("user_id") or data.get("pin")
        return {
            "username": username,
            "email": data.get("email") or "",
            "first_name": first_name,
            "last_name": last_name,
        }

registry.register(EgovUzProvider)
