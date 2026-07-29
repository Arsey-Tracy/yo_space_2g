# pyrefly: ignore [missing-import]
from django.urls import path, include
# pyrefly: ignore [missing-import]
from rest_framework.routers import DefaultRouter
# pyrefly: ignore [missing-import]
from .views import (
    DashboardStatsView, SpaceViewSet, MergeSpacesView,
    SpaceMemberViewSet, ImportMembersCSVView, ExportMembersCSVView,
    BroadcastViewSet, SurveyViewSet,
    ussd_callback, voice_callback, conference_control,
    active_listeners, sms_delivery_report
)

router = DefaultRouter()
router.register(r'spaces', SpaceViewSet, basename='space')
router.register(r'broadcasts', BroadcastViewSet, basename='broadcast')
router.register(r'surveys', SurveyViewSet, basename='survey')

urlpatterns = [
    path('dashboard/stats/', DashboardStatsView.as_view(), name='dashboard-stats'),
    path('spaces/merge/', MergeSpacesView.as_view(), name='space-merge'),
    path('spaces/<int:space_pk>/members/', SpaceMemberViewSet.as_view({'get': 'list', 'post': 'create'}), name='space-members-list'),
    path('spaces/<int:space_pk>/members/<int:pk>/', SpaceMemberViewSet.as_view({'get': 'retrieve', 'put': 'update', 'delete': 'destroy'}), name='space-members-detail'),
    path('spaces/<int:space_pk>/members/import-csv/', ImportMembersCSVView.as_view(), name='space-members-import'),
    path('spaces/<int:space_pk>/members/export/', ExportMembersCSVView.as_view(), name='space-members-export'),
    
    # Include Router
    path('', include(router.urls)),

    # Africa's Talking Telephony & SMS Webhooks
    path('ussd/', ussd_callback, name='ussd-callback'),
    path('voice/', voice_callback, name='voice-callback'),
    path('conference/', conference_control, name='conference-control'),
    path('active-listeners/', active_listeners, name='active-listeners'),
    path('dlr/', sms_delivery_report, name='sms-delivery-report'),
]
