from rest_framework import status, permissions, viewsets
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework_simplejwt.tokens import RefreshToken
from .models import CustomUser, Organization, Member
from .serializers import (
    CustomUserSerializer, OrganizationSerializer,
    RegisterSerializer, MemberSerializer
)


class RegisterView(APIView):
    permission_classes = [permissions.AllowAny]

    def post(self, request):
        serializer = RegisterSerializer(data=request.data)
        if serializer.is_valid():
            user, org = serializer.save()
            refresh = RefreshToken.for_user(user)

            res_data = {
                'user': CustomUserSerializer(user).data,
                'organization': OrganizationSerializer(org).data,
                'tokens': {
                    'refresh': str(refresh),
                    'access': str(refresh.access_token),
                }
            }

            return Response(res_data, status=status.HTTP_201_CREATED)
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


class OrganizationView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        org = Organization.objects.filter(owner=request.user).first()
        if not org:
            # Check membership
            member = Member.objects.filter(user=request.user).first()
            if member:
                org = member.organization

        if not org:
            return Response({'detail': 'No organization found.'}, status=status.HTTP_404_NOT_FOUND)

        serializer = OrganizationSerializer(org)
        return Response(serializer.data)

    def put(self, request):
        org = Organization.objects.filter(owner=request.user).first()
        if not org:
            return Response({'detail': 'Only organization owner can update settings.'}, status=status.HTTP_403_FORBIDDEN)

        serializer = OrganizationSerializer(org, data=request.data, partial=True)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class MemberViewSet(viewsets.ModelViewSet):
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = MemberSerializer

    def get_queryset(self):
        org = Organization.objects.filter(owner=self.request.user).first()
        if org:
            return Member.objects.filter(organization=org)
        return Member.objects.none()
