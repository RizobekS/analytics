# analytics/views_common.py
from ingest.models import HandleRegistry

def user_can_edit_handle(user, handle: str) -> bool:
    if not user or not user.is_authenticated:
        return False
    if getattr(user, "is_superuser", False):
        return True
    hr = HandleRegistry.objects.filter(handle=handle).first()
    if not hr:
        return False
    return hr.allowed_users.filter(id=user.id).exists()
