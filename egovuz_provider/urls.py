from django.urls import path
from .views import broker_login, oauth2_callback_broker

urlpatterns = [
    path("login/", broker_login, name="egovuz_login"),
    path("callback/", oauth2_callback_broker, name="egovuz_callback"),
]
