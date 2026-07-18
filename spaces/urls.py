from django.urls import path
from .views import active_listeners, conference_control, ussd_callback, voice_callback

urlpatterns = [
    path("ussd/", ussd_callback, name="ussd-callback"),
    path("voice/", voice_callback, name="voice-callback"),
    path("conference/", conference_control, name="conference-control"),
    path("active-listeners/", active_listeners, name="active-listeners"),
]
