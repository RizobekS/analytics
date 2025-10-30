from allauth.account.adapter import DefaultAccountAdapter
from allauth.socialaccount.adapter import DefaultSocialAccountAdapter
from django.contrib.auth import get_user_model

User = get_user_model()

class NoSignupAccountAdapter(DefaultAccountAdapter):
    """Запретить обычную регистрацию (форма signup)."""
    def is_open_for_signup(self, request):
        return False  # /accounts/signup/ станет недоступен (404)

class NoSignupSocialAdapter(DefaultSocialAccountAdapter):
    """Запретить создание новых учёток через соц.логины, но
    автопривязывать к уже созданным пользователям по совпадению e-mail.
    """
    def is_open_for_signup(self, request, sociallogin):
        return False  # запрещаем auto-signup через провайдеров

    def pre_social_login(self, request, sociallogin):
        # Если соц.аккаунт уже привязан — ничего не делаем.
        if sociallogin.is_existing:
            return

        data = sociallogin.account.extra_data or {}
        email = (sociallogin.user and sociallogin.user.email) or data.get("email")
        username = (sociallogin.user and sociallogin.user.username) or data.get("user_id") or data.get("pin")

        user = None
        if email:
            try:
                user = User.objects.get(email__iexact=email)
            except User.DoesNotExist:
                pass

        if not user and username:
            try:
                user = User.objects.get(username__iexact=username)
            except User.DoesNotExist:
                pass

        if user:
            sociallogin.connect(request, user)
