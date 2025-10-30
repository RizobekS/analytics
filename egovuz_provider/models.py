from django.conf import settings
from django.db import models

class UserProfile(models.Model):
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="profile")

    # поля из id.egov.uz
    egov_uid = models.CharField(max_length=64, blank=True, null=True, unique=True)  # user_id или pin
    pin = models.CharField(max_length=32, blank=True, null=True)
    full_name = models.CharField(max_length=255, blank=True, null=True)
    first_name = models.CharField(max_length=128, blank=True, null=True)
    last_name  = models.CharField(max_length=128, blank=True, null=True)
    middle_name = models.CharField(max_length=128, blank=True, null=True)

    # тех.инфо
    last_sync = models.DateTimeField(blank=True, null=True)

    def __str__(self):
        u = getattr(self, "user", None)
        return f"Profile({getattr(u, 'username', 'no-user')}, {self.egov_uid})"
