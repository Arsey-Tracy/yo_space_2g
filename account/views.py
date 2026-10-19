from django.db import transaction
from django.db.models import Q
from rest_framework import serializers, status, permissions, viewsets
from rest_framework.throttling import ScopedRateThrottle
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework_simplejwt.tokens import RefreshToken
from .models import Organization, Member
from .serializers import (
    CustomUserSerializer, OrganizationSerializer,
    RegisterSerializer, MemberSerializer, LoginSerializer,
    OrganizationCreateSerializer,
)


class RegisterView(APIView):
    permission_classes = [permissions.AllowAny]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "auth_register"

    def post(self, request):
        serializer = RegisterSerializer(data=request.data)
        if serializer.is_valid():
            user, org = serializer.save()
            refresh = RefreshToken.for_user(user)

            res_data = {
                'user': CustomUserSerializer(user).data,
                'organization': OrganizationSerializer(org).data if org else None,
                'tokens': {
                    'refresh': str(refresh),
                    'access': str(refresh.access_token),
                }
            }

            return Response(res_data, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

class LoginView(APIView):
    permission_classes = [permissions.AllowAny]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "auth_login"

    def post(self, request):
        serializer = LoginSerializer(data=request.data, context={'request': request})
        if serializer.is_valid():
            user = serializer.validated_data['user']
            org = serializer.validated_data.get('organization')
            refresh = RefreshToken.for_user(user)

            res_data = {
                'user': CustomUserSerializer(user).data,
                'organization': OrganizationSerializer(org).data if org else None,
                'tokens': {
                    'refresh': str(refresh),
                    'access': str(refresh.access_token),
                }
            }
            return Response(res_data, status=status.HTTP_200_OK)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class ProfileView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        serializer = CustomUserSerializer(request.user)
        return Response(serializer.data)

    def put(self, request):
        serializer = CustomUserSerializer(request.user, data=request.data, partial=True)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class MeView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        memberships = Member.objects.filter(user=request.user).select_related(
            "organization"
        )
        organizations = {}
        for membership in memberships:
            organizations[membership.organization_id] = {
                "id": membership.organization_id,
                "name": membership.organization.name,
                "role": membership.role,
            }

        for organization in Organization.objects.filter(owner=request.user):
            organizations.setdefault(
                organization.id,
                {"id": organization.id, "name": organization.name, "role": "owner"},
            )

        organization_list = list(organizations.values())
        requested_id = request.headers.get("X-Organization-ID")
        active_organization = None
        if requested_id:
            active_organization = organizations.get(
                int(requested_id) if requested_id.isdigit() else None
            )
        if active_organization is None and organization_list:
            active_organization = organization_list[0]

        return Response(
            {
                "user": CustomUserSerializer(request.user).data,
                "organizations": organization_list,
                "active_organization": active_organization,
            }
        )


class OrganizationView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        organizations = Organization.objects.filter(
            Q(owner=request.user) | Q(members__user=request.user)
        ).distinct()
        organization_id = request.headers.get("X-Organization-ID")
        if organization_id:
            try:
                org = organizations.filter(pk=int(organization_id)).first()
            except (TypeError, ValueError):
                org = None
        else:
            org = Organization.objects.filter(owner=request.user).first()
            if org is None:
                membership = (
                    Member.objects.filter(user=request.user)
                    .select_related("organization")
                    .first()
                )
                org = membership.organization if membership else None

        if not org:
            return Response(
                {"detail": "No organization found."},
                status=status.HTTP_404_NOT_FOUND,
            )

        serializer = OrganizationSerializer(org)
        return Response(serializer.data)

    def put(self, request):
        organizations = Organization.objects.filter(owner=request.user)
        organization_id = request.headers.get("X-Organization-ID")
        if organization_id:
            try:
                org = organizations.filter(pk=int(organization_id)).first()
            except (TypeError, ValueError):
                org = None
        else:
            org = organizations.first()
        if not org:
            return Response(
                {"detail": "Only organization owners can update settings."},
                status=status.HTTP_403_FORBIDDEN,
            )

        serializer = OrganizationSerializer(org, data=request.data, partial=True)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    def post(self, request):
        serializer = OrganizationCreateSerializer(
            data=request.data,
            context={"request": request},
        )
        if serializer.is_valid():
            with transaction.atomic():
                organization = serializer.save()
            return Response(
                OrganizationSerializer(organization).data,
                status=status.HTTP_201_CREATED,
            )
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class MemberViewSet(viewsets.ModelViewSet):
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = MemberSerializer

    def get_queryset(self):
        return Member.objects.filter(
            organization__owner=self.request.user
        ).select_related("organization", "user")

    def perform_create(self, serializer):
        organization = serializer.validated_data["organization"]
        if organization.owner_id != self.request.user.id:
            raise serializers.ValidationError(
                {"organization": "You can only manage members of your own organizations."}
            )
        serializer.save()

    def perform_update(self, serializer):
        organization = serializer.validated_data.get(
            "organization", serializer.instance.organization
        )
        if organization.owner_id != self.request.user.id:
            raise serializers.ValidationError(
                {"organization": "You can only manage members of your own organizations."}
            )
        serializer.save()
