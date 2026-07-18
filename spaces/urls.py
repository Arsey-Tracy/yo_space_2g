from django.urls import path
from .views import ussd_callback


path("ussd/", ussd_callback, name="ussd-callback")