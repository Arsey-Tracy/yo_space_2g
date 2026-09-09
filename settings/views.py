from django.shortcuts import render
from rest_framework import permissions, status
from rest_framework.response import Response
from rest_framework.views import APIView

from account.models import Member, Organization
from .models import OrganizationSetting
from .serializers import OrganizationSettingSerializer


class OrganizationSettingsView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get_organization(self, user):
        org = Organization.objects.filter(owner=user).first()
        if org:
            return org
        member = Member.objects.filter(user=user).first()
        return member.organization if member else None

    def get(self, request):
        org = self.get_organization(request.user)
        if not org:
            return Response({'detail': 'Organization not found.'}, status=status.HTTP_404_NOT_FOUND)

        setting, _ = OrganizationSetting.objects.get_or_create(organization=org)
        return Response(OrganizationSettingSerializer(setting).data)

    def put(self, request):
        org = self.get_organization(request.user)
        if not org:
            return Response({'detail': 'Organization not found.'}, status=status.HTTP_404_NOT_FOUND)

        setting, _ = OrganizationSetting.objects.get_or_create(organization=org)
        serializer = OrganizationSettingSerializer(setting, data=request.data, partial=True)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
