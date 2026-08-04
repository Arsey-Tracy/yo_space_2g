from django.urls import path
from .views import voice_callback, conference_control, active_listeners

urlpatterns = [
    path('voice/', voice_callback, name='voice-callback'),
    path('conference/', conference_control, name='conference-control'),
    path('active-listeners/', active_listeners, name='active-listeners'),
]
