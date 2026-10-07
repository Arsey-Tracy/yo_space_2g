from __future__ import annotations

import csv
import io
import logging
from datetime import datetime
from django.shortcuts import get_object_or_404
from django.conf import settings
from django.db import transaction
from django.http import HttpResponse
from django.utils import timezone

from rest_framework import status, permissions, viewsets, serializers
from rest_framework.exceptions import ValidationError
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.decorators import action
from rest_framework.parsers import MultiPartParser, FormParser

from account.models import Organization, Member

from sms.models import Broadcast
from sms.serializers import BroadcastSerializer
from voice.views import trigger_outbound_space_calls
from .permissions import IsOrganizationOwner

from .models import Space, SpaceMember
from .serializers import SpaceSerializer, SpaceMemberSerializer, MergeSpacesSerializer

logger = logging.getLogger("yospaces")


def _normalize_phone(phone: str) -> str:
    phone = (phone or "").strip().replace(" ", "")
    if not phone:
        return phone
    if phone.startswith("+"):
        return phone
    if phone.startswith("0"):
        return "+256" + phone[1:]
    return "+" + phone


# ==========================================
# REST API VIEWS FOR DASHBOARD & SPACES
# ==========================================


class DashboardStatsView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get_space(self):
        return get_object_or_404(
            Space, id=self.kwargs["space_pk"], organization__owner=self.request.user
        )

    def get_queryset(self):
        return SpaceMember.objects.filter(
            space__id=self.kwargs["space_pk"],
            space__organization__owner=self.request.user,
        ).select_related("space", "user")

    def perform_create(self, serializer):
        """
        Never trust the nested URL alone.
        Resolve the Space through the authenticated user's organization before creating the member.
        """
        space = self.get_space()
        serializer.save(space=space)

    def get(self, request):
        org = Organization.objects.filter(owner=request.user).first()
        if not org:
            member = Member.objects.filter(user=request.user).first()
            if member:
                org = member.organization

        if not org:
            return Response(
                {"detail": "Organization not found."}, status=status.HTTP_404_NOT_FOUND
            )

        plan = None  # No subscription plan
        spaces = Space.objects.filter(organization=org)
        total_spaces = spaces.count()
        total_members = (
            SpaceMember.objects.filter(space__in=spaces)
            .values("phone_number")
            .distinct()
            .count()
        )

        # Broadcasts sent this month
        now = timezone.now()
        start_of_month = datetime(now.year, now.month, 1, tzinfo=now.tzinfo)
        broadcasts_this_month = Broadcast.objects.filter(
            space__in=spaces, status="sent", sent_at__gte=start_of_month
        ).count()

        wallet = getattr(org, "wallet", None)
        if not wallet:
            from wallet.models import Wallet

            wallet = Wallet.objects.create(organization=org)

        return Response(
            {
                "organization": org.name,
                "sms_balance": wallet.balance_credits,
                "cash_balance_ugx": wallet.cash_balance_ugx,
                "total_spaces": total_spaces,
                "total_members": total_members,
                "broadcasts_sent_this_month": broadcasts_this_month,
                "recent_broadcasts": BroadcastSerializer(
                    Broadcast.objects.filter(space__in=spaces)[:5], many=True
                ).data,
            }
        )


class SpaceViewSet(viewsets.ModelViewSet):
    serializer_class = SpaceSerializer
    permission_classes = [permissions.IsAuthenticated, IsOrganizationOwner]

    def get_queryset(self):
        return Space.objects.filter(
            organization__owner=self.request.user
        ).select_related("organization")

    def perform_create(self, serializer):
        org = Organization.objects.filter(owner=self.request.user).first()
        if not org:
            raise serializers.ValidationError(
                "Only organization owners can create spaces."
            )

        serializer.save(
            organization=org,
            host_phone=self.request.user.phone
            or getattr(settings, "AT_VOICE_NUMBER", "+256323200925"),
        )

    @action(detail=True, methods=["post"], url_path="go-live")
    def go_live_api(self, request, pk=None):
        space = self.get_object()
        space.is_active = True
        space.save(update_fields=["is_active"])

        invited_count = trigger_outbound_space_calls(space)

        return Response(
            {
                "message": f"Space '{space.name}' is now LIVE.",
                "pin": space.pin,
                "invited_callers_count": invited_count,
            }
        )


class MergeSpacesView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        serializer = MergeSpacesSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        org = Organization.objects.filter(owner=request.user).first()
        if not org:
            return Response(
                {"detail": "Organization not found."}, status=status.HTTP_404_NOT_FOUND
            )

        # Merge spaces allowed without subscription checks

        source_id = serializer.validated_data["source_space_id"]
        target_id = serializer.validated_data["target_space_id"]

        source_space = Space.objects.filter(id=source_id, organization=org).first()
        target_space = Space.objects.filter(id=target_id, organization=org).first()

        if not source_space or not target_space:
            return Response(
                {"detail": "One or both spaces were not found."},
                status=status.HTTP_404_NOT_FOUND,
            )

        with transaction.atomic():
            for member in source_space.members.all():
                if not SpaceMember.objects.filter(
                    space=target_space, phone_number=member.phone_number
                ).exists():
                    member.space = target_space
                    member.save()

            if not serializer.validated_data.get("keep_source_space", False):
                source_space.delete()

        return Response(
            {
                "message": f"Successfully merged space into '{target_space.name}'.",
                "target_space": SpaceSerializer(target_space).data,
            }
        )


class SpaceMemberViewSet(viewsets.ModelViewSet):
    permission_classes = [permissions.IsAuthenticated, IsOrganizationOwner]
    serializer_class = SpaceMemberSerializer

    def get_space(self):
        return get_object_or_404(
            Space,
            id=self.kwargs.get("space_pk"),
            organization__owner=self.request.user,
        )

    def get_queryset(self):
        space = self.get_space()
        return SpaceMember.objects.filter(space=space).select_related("space", "user")

    def get_object(self):
        space = self.get_space()
        return get_object_or_404(
            SpaceMember,
            pk=self.kwargs.get("pk"),
            space=space,
        )

    def perform_create(self, serializer):
        space = self.get_space()
        serializer.save(space=space)


class ImportMembersCSVView(APIView):
    permission_classes = [permissions.IsAuthenticated]
    parser_classes = [MultiPartParser, FormParser]

    def post(self, request, space_pk=None):
        space = get_object_or_404(
            Space,
            id=space_pk,
            organization__owner=request.user,
        )

        file_obj = request.FILES.get("file")
        if not file_obj:
            return Response(
                {"detail": "No CSV file provided."}, status=status.HTTP_400_BAD_REQUEST
            )

        decoded_file = file_obj.read().decode("utf-8", errors="ignore")
        io_string = io.StringIO(decoded_file)
        reader = csv.DictReader(io_string)

        imported_count = 0
        skipped_count = 0

        for row in reader:
            phone = (
                row.get("phone")
                or row.get("phone_number")
                or row.get("Phone")
                or row.get("Mobile")
                or row.get("mobile")
            )
            if not phone:
                continue
            phone = _normalize_phone(phone)
            name = row.get("name") or row.get("Name") or row.get("full_name") or ""
            role = row.get("role") or row.get("Role") or "member"

            member, created = SpaceMember.objects.get_or_create(
                space=space, phone_number=phone, defaults={"name": name, "role": role}
            )
            if created:
                imported_count += 1
            else:
                skipped_count += 1

        return Response(
            {
                "message": f"Import completed: {imported_count} imported, {skipped_count} existing skipped.",
                "total_space_members": space.members.count(),
            }
        )


class ExportMembersCSVView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request, space_pk=None):
        space = Space.objects.filter(
            id=space_pk, organization__owner=request.user
        ).first()
        if not space:
            return Response(
                {"detail": "Space not found."}, status=status.HTTP_404_NOT_FOUND
            )

        response = HttpResponse(content_type="text/csv")
        response["Content-Disposition"] = (
            f'attachment; filename="space_{space.id}_members.csv"'
        )

        writer = csv.writer(response)
        writer.writerow(["ID", "Name", "Phone Number", "Role", "Joined At"])

        for m in space.members.all():
            writer.writerow(
                [
                    m.id,
                    m.name or "",
                    m.phone_number,
                    m.role,
                    m.joined_at.strftime("%Y-%m-%d %H:%M:%S"),
                ]
            )

        return response

