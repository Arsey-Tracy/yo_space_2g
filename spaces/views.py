from __future__ import annotations

import csv
import io
import logging
import re
from datetime import datetime

from django.conf import settings
from django.db import transaction
from django.http import HttpResponse
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt

from rest_framework import status, permissions, viewsets, serializers
from rest_framework.exceptions import ValidationError
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.decorators import action
from rest_framework.parsers import MultiPartParser, FormParser

from account.models import Organization, CustomUser, Member
# Subscription model removed; unlimited plan defaults
from sms.models import Broadcast
from sms.serializers import BroadcastSerializer
from sms.views import send_bulk_sms
from voice.views import trigger_outbound_space_calls
from survey.models import Survey

from .models import Space, SpaceMember
from .serializers import (
    SpaceSerializer, SpaceMemberSerializer, MergeSpacesSerializer
)

logger = logging.getLogger("yospaces")


def _plain(text: str) -> HttpResponse:
    return HttpResponse(text, content_type="text/plain")


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

    def get(self, request):
        org = Organization.objects.filter(owner=request.user).first()
        if not org:
            member = Member.objects.filter(user=request.user).first()
            if member:
                org = member.organization

        if not org:
            return Response({'detail': 'Organization not found.'}, status=status.HTTP_404_NOT_FOUND)

        # path("api/billing/", include("billing.urls")),
        plan = None  # No subscription plan
        spaces = Space.objects.filter(organization=org)
        total_spaces = spaces.count()
        total_members = SpaceMember.objects.filter(space__in=spaces).values('phone_number').distinct().count()

        # Broadcasts sent this month
        now = timezone.now()
        start_of_month = datetime(now.year, now.month, 1, tzinfo=now.tzinfo)
        broadcasts_this_month = Broadcast.objects.filter(
            space__in=spaces, status='sent', sent_at__gte=start_of_month
        ).count()

        wallet = getattr(org, 'wallet', None)
        if not wallet:
            from wallet.models import Wallet
            wallet = Wallet.objects.create(organization=org)

        return Response({
            'organization': org.name,
            'sms_balance': wallet.balance_credits,
            'cash_balance_ugx': wallet.cash_balance_ugx,
            'total_spaces': total_spaces,
            'total_members': total_members,
            'broadcasts_sent_this_month': broadcasts_this_month,
            'recent_broadcasts': BroadcastSerializer(
                Broadcast.objects.filter(space__in=spaces)[:5], many=True
            ).data
        })


class SpaceViewSet(viewsets.ModelViewSet):
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = SpaceSerializer

    def get_queryset(self):
        org = Organization.objects.filter(owner=self.request.user).first()
        if org:
            return Space.objects.filter(organization=org)
        return Space.objects.none()

    def perform_create(self, serializer):
        org = Organization.objects.filter(owner=self.request.user).first()
        if not org:
            raise serializers.ValidationError("Only organization owners can create spaces.")

        # No subscription limits; allow unlimited spaces
        max_allowed = None

        # No space limit enforcement

        serializer.save(
            organization=org,
            host_phone=self.request.user.phone or getattr(settings, "AT_VOICE_NUMBER", "+256323200925")
        )

    @action(detail=True, methods=['post'], url_path='go-live')
    def go_live_api(self, request, pk=None):
        space = self.get_object()
        space.is_active = True
        space.save(update_fields=['is_active'])

        invited_count = trigger_outbound_space_calls(space)

        return Response({
            'message': f"Space '{space.name}' is now LIVE.",
            'pin': space.pin,
            'invited_callers_count': invited_count
        })


class MergeSpacesView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        serializer = MergeSpacesSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        org = Organization.objects.filter(owner=request.user).first()
        if not org:
            return Response({'detail': 'Organization not found.'}, status=status.HTTP_404_NOT_FOUND)

        # Merge spaces allowed without subscription checks

        source_id = serializer.validated_data['source_space_id']
        target_id = serializer.validated_data['target_space_id']

        source_space = Space.objects.filter(id=source_id, organization=org).first()
        target_space = Space.objects.filter(id=target_id, organization=org).first()

        if not source_space or not target_space:
            return Response({'detail': 'One or both spaces were not found.'}, status=status.HTTP_404_NOT_FOUND)

        with transaction.atomic():
            for member in source_space.members.all():
                if not SpaceMember.objects.filter(space=target_space, phone_number=member.phone_number).exists():
                    member.space = target_space
                    member.save()

            if not serializer.validated_data.get('keep_source_space', False):
                source_space.delete()

        return Response({
            'message': f"Successfully merged space into '{target_space.name}'.",
            'target_space': SpaceSerializer(target_space).data
        })


class SpaceMemberViewSet(viewsets.ModelViewSet):
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = SpaceMemberSerializer

    def get_queryset(self):
        space_id = self.kwargs.get('space_pk')
        if space_id:
            return SpaceMember.objects.filter(space_id=space_id)
        return SpaceMember.objects.none()

    def perform_create(self, serializer):
        space_id = self.kwargs.get('space_pk')
        space = Space.objects.get(id=space_id)
        org = space.organization
        # No member limit enforcement; unlimited members

        serializer.save(space=space)


class ImportMembersCSVView(APIView):
    permission_classes = [permissions.IsAuthenticated]
    parser_classes = [MultiPartParser, FormParser]

    def post(self, request, space_pk=None):
        space = Space.objects.filter(id=space_pk, organization__owner=request.user).first()
        if not space:
            return Response({'detail': 'Space not found.'}, status=status.HTTP_404_NOT_FOUND)

        file_obj = request.FILES.get('file')
        if not file_obj:
            return Response({'detail': 'No CSV file provided.'}, status=status.HTTP_400_BAD_REQUEST)

        decoded_file = file_obj.read().decode('utf-8', errors='ignore')
        io_string = io.StringIO(decoded_file)
        reader = csv.DictReader(io_string)

        imported_count = 0
        skipped_count = 0

        for row in reader:
            phone = row.get('phone') or row.get('phone_number') or row.get('Phone') or row.get('Mobile') or row.get('mobile')
            if not phone:
                continue
            phone = _normalize_phone(phone)
            name = row.get('name') or row.get('Name') or row.get('full_name') or ''
            role = row.get('role') or row.get('Role') or 'member'

            member, created = SpaceMember.objects.get_or_create(
                space=space,
                phone_number=phone,
                defaults={'name': name, 'role': role}
            )
            if created:
                imported_count += 1
            else:
                skipped_count += 1

        return Response({
            'message': f"Import completed: {imported_count} imported, {skipped_count} existing skipped.",
            'total_space_members': space.members.count()
        })


class ExportMembersCSVView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request, space_pk=None):
        space = Space.objects.filter(id=space_pk, organization__owner=request.user).first()
        if not space:
            return Response({'detail': 'Space not found.'}, status=status.HTTP_404_NOT_FOUND)

        response = HttpResponse(content_type='text/csv')
        response['Content-Disposition'] = f'attachment; filename="space_{space.id}_members.csv"'

        writer = csv.writer(response)
        writer.writerow(['ID', 'Name', 'Phone Number', 'Role', 'Joined At'])

        for m in space.members.all():
            writer.writerow([m.id, m.name or '', m.phone_number, m.role, m.joined_at.strftime('%Y-%m-%d %H:%M:%S')])

        return response


# ==========================================
# AFRICA'S TALKING USSD CALLBACK
# ==========================================

_ussd_sessions = {}


def _get_session(phone_number: str) -> dict:
    if phone_number not in _ussd_sessions:
        _ussd_sessions[phone_number] = {
            "state": "main_menu",
            "space_name": None,
            "survey_id": None,
            "question_index": 0,
            "step": 0,
            "browse_ids": [],
        }
    return _ussd_sessions[phone_number]


def _update_session(phone_number: str, **kwargs) -> None:
    session = _get_session(phone_number)
    session.update(kwargs)


def _clear_session(phone_number: str) -> None:
    if phone_number in _ussd_sessions:
        del _ussd_sessions[phone_number]


def _current_input(text: str) -> str:
    parts = (text or "").split("*")
    return parts[-1].strip() if parts else ""


@csrf_exempt
def ussd_callback(request):
    """
    USSD Callback Handler with Caller-Based Role Routing:
    - If dialing phone belongs to an Organization Owner/Host -> Show Host/Manage Space Menu
    - If dialing phone belongs to an End User / Member -> Show Join Space, Browse Spaces, Active Surveys Menu
    """
    if request.method != "POST":
        return _plain("END Invalid request method.")

    phone_number = _normalize_phone(request.POST.get("phoneNumber", ""))
    text = (request.POST.get("text", "") or "").strip()
    current = _current_input(text)
    session = _get_session(phone_number)

    is_org_host = CustomUser.objects.filter(phone=phone_number).exists() or \
                  Organization.objects.filter(owner__phone=phone_number).exists() or \
                  Space.objects.filter(host_phone=phone_number).exists()

    if text == "":
        _update_session(phone_number, state="main_menu", space_name=None, step=0)
        if is_org_host:
            return _plain(
                "CON Welcome Host to YoSpaces\n"
                "1. Host a Space\n"
                "2. Manage My Spaces\n"
                "3. Broadcast SMS\n"
                "4. Browse Public Spaces\n"
                "5. Exit"
            )
        else:
            return _plain(
                "CON Welcome to YoSpaces\n"
                "1. Join Space via PIN\n"
                "2. Browse Public Spaces\n"
                "3. Take Active Surveys\n"
                "4. About YoSpaces\n"
                "5. Exit"
            )

    # Host Workflow
    if is_org_host:
        if text == "1":
            _update_session(phone_number, state="host_space_name", step=1)
            return _plain("CON Enter a name for your Space:")

        if session["state"] == "host_space_name":
            space_name = current[:100]
            space, _created = Space.objects.get_or_create(
                name=space_name,
                host_phone=phone_number,
                defaults={"pin": ''.join(re.findall(r'\d', str(hash(space_name))))[:4] or "1234"}
            )
            _clear_session(phone_number)
            return _plain(f"END Space '{space.name}' created!\nPIN: {space.pin}\nMembers can dial in to join.")

        if text == "2":
            spaces = list(Space.objects.filter(host_phone=phone_number)[:5])
            if not spaces:
                return _plain("END You have no active spaces.")
            lines = ["CON My Spaces:"]
            for idx, sp in enumerate(spaces, start=1):
                lines.append(f"{idx}. {sp.name} (PIN: {sp.pin})")
            return _plain("\n".join(lines))

        if text == "3":
            _update_session(phone_number, state="host_broadcast_msg")
            return _plain("CON Enter broadcast SMS message for your members:")

        if session["state"] == "host_broadcast_msg":
            msg = current
            space = Space.objects.filter(host_phone=phone_number).first()
            if not space:
                return _plain("END No space found to send broadcast.")
            org = space.organization
            recipients = list(space.members.values_list('phone_number', flat=True))
            send_bulk_sms(recipients, msg, sender_id=org.sender_id if org else None, org_name=org.name if org else None)
            _clear_session(phone_number)
            return _plain(f"END Broadcast sent to {len(recipients)} members of {space.name}.")

    # End-User / Member Workflow
    if text == "1" and not is_org_host:
        _update_session(phone_number, state="join_space_pin")
        return _plain("CON Enter 4-digit Space PIN:")

    if session["state"] == "join_space_pin":
        pin = current.strip()
        space = Space.objects.filter(pin=pin).first()
        if not space:
            return _plain("END Invalid PIN. Space not found.")

        SpaceMember.objects.get_or_create(space=space, phone_number=phone_number)
        _clear_session(phone_number)
        return _plain(
            f"END Registered for '{space.name}'!\n"
            f"Dial the YoSpaces Voice line and enter PIN {space.pin} to join voice calls."
        )

    if (text == "2" and not is_org_host) or (text == "4" and is_org_host):
        spaces = list(Space.objects.filter(is_public=True).order_by('-created_at')[:5])
        if not spaces:
            return _plain("END No public spaces available.")
        lines = ["CON Public Spaces:"]
        for idx, sp in enumerate(spaces, start=1):
            lines.append(f"{idx}. {sp.name} (PIN: {sp.pin})")
        return _plain("\n".join(lines))

    if text == "3" and not is_org_host:
        surveys = list(Survey.objects.filter(is_active=True).order_by('-created_at')[:5])
        if not surveys:
            return _plain("END No active surveys available.")
        lines = ["CON Active Surveys:"]
        for idx, s in enumerate(surveys, start=1):
            lines.append(f"{idx}. {s.title}")
        _update_session(phone_number, state="take_survey", survey_id=surveys[0].id)
        return _plain("\n".join(lines))

    if text == "4" and not is_org_host:
        _clear_session(phone_number)
        return _plain("END Yo-Spaces is a 2G community communication platform powered by SMS & Voice.")

    if text == "5":
        _clear_session(phone_number)
        return _plain("END Thank you for using Yo-Spaces.")

    return _plain("END Invalid selection. Goodbye.")
