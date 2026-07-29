from django.urls import path, include
from rest_framework.routers import DefaultRouter
from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView
from .views import RegisterView, ProfileView, OrganizationView, MemberViewSet

router = DefaultRouter()
router.register(r'members', MemberViewSet, basename='org-member')

urlpatterns = [
    path('register/', RegisterView.as_view(), name='auth-register'),
    path('register', RegisterView.as_view()),
    path('login/', TokenObtainPairView.as_view(), name='token_obtain_pair'),
    path('login', TokenObtainPairView.as_view()),
    path('token/refresh/', TokenRefreshView.as_view(), name='token_refresh'),
    path('token/refresh', TokenRefreshView.as_view()),
    path('profile/', ProfileView.as_view(), name='user-profile'),
    path('profile', ProfileView.as_view()),
    path('organization/', OrganizationView.as_view(), name='organization-detail'),
    path('organization', OrganizationView.as_view()),
    path('organization/', include(router.urls)),
]
