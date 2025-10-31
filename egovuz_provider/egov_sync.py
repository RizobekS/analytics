from django.dispatch import receiver
from allauth.account.signals import user_logged_in
from allauth.socialaccount.signals import social_account_added, social_account_updated
from allauth.socialaccount.models import SocialAccount
from django.utils import timezone

def _extract_egov_fields(extra):
    pin = (extra.get("pin") or "").strip()
    return {
        "egov_uid":(extra.get("user_id") or pin),
        "pin": pin,
        "full_name": extra.get("full_name"),
        "first_name": extra.get("first_name") or extra.get("name"),
        "last_name": extra.get("sur_name"),
        "middle_name": extra.get("mid_name"),
    }

def _sync_profile(user):
    try:
        sa = SocialAccount.objects.get(user=user, provider="egovuz")
    except SocialAccount.DoesNotExist:
        return
    data = sa.extra_data or {}
    fields = _extract_egov_fields(data)

    profile = getattr(user, "profile", None)
    if not profile:
        from .models import UserProfile
        profile, _ = UserProfile.objects.get_or_create(user=user)

    changed = False
    for k, v in fields.items():
        if v and getattr(profile, k) != v:
            setattr(profile, k, v)
            changed = True

    if changed:
        profile.last_sync = timezone.now()
        profile.save()

@receiver(user_logged_in)
def on_user_logged_in(request, user, **kwargs):
    _sync_profile(user)

@receiver(social_account_added)
def on_social_account_added(request, sociallogin, **kwargs):
    _sync_profile(sociallogin.user)

@receiver(social_account_updated)
def on_social_account_updated(request, sociallogin, **kwargs):
    _sync_profile(sociallogin.user)
