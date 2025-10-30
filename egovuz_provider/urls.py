from django.urls import path
from .views import oauth2_login, oauth2_callback

urlpatterns = [
    path("login/", oauth2_login, name="egovuz_login"),
    path("callback/", oauth2_callback, name="egovuz_callback"),
]
