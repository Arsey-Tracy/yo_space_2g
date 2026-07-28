from __future__ import annotations

import csv
import io
import json
import logging
import re
import urllib.error
import urllib.parse
import urllib.request
from typing import Optional
from datetime import datetime

import xml.sax.saxutils as sx
from django.conf import settings
from django.db import transaction
from django.http import HttpResponse, JsonResponse
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt

from rest_framework import status, permissions, viewsets
from rest_framework.exceptions import ValidationError
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.decorators import action
from rest_framework.parsers import MultiPartParser, FormParser

from account.models import Organization, CustomUser, Member
from subscriptions.models import Subscription, SMSUsageLog
from .models import (
    Space, SpaceMember, ActiveSpaceParticipant,
    Broadcast, Survey, SurveyQuestion, SurveyResponse
)
from .serializers import (
    SpaceSerializer, SpaceMemberSerializer, BroadcastSerializer,
    SurveySerializer, SurveyQuestionSerializer, SurveyResponseSerializer,
    MergeSpacesSerializer
)

try:
    import africastalking  # type: ignore
except Exception:  # pragma: no cover
    africastalking = None

logger = logging.getLogger("yospaces")

AT_VOICE_NUMBER = getattr(settings, "AT_VOICE_NUMBER", "+256323200925")
AFRICASTALKING_LIVE_USERNAME = getattr(settings, "AFRICASTALKING_LIVE_USERNAME", "yo_space")
AFRICASTALKING_LIVE_API_KEY = getattr(settings, "AFRICASTALKING_LIVE_API_KEY", "")
AT_CONFERENCE_URL = "https://voice.africastalking.com/conference"
AT_CALL_URL = "https://voice.africastalking.com/call"

if africastalking and AFRICASTALKING_LIVE_API_KEY:
    try:
        africastalking.initialize(AFRICASTALKING_LIVE_USERNAME, AFRICASTALKING_LIVE_API_KEY)
    except Exception as exc:
        logger.warning("Africa's Talking SDK initialization failed: %s", exc)


def _plain(text: str) -> HttpResponse:
    return HttpResponse(text, content_type="text/plain")


def _xml(text: str) -> HttpResponse:
    return HttpResponse(text, content_type="text/xml")


def _normalize_phone(phone: str) -> str:
    phone = (phone or "").strip().replace(" ", "")
    if not phone:
        return phone
    if phone.startswith("+"):
        return phone
    if phone.startswith("0"):
        return "+256" + phone[1:]
    return "+" + phone


def send_bulk_sms(phone_numbers: list[str], message: str, sender_id: Optional[str] = None) -> dict:
    """
    Sends bulk SMS via Africa's Talking API and returns result dictionary.
    """
    normalized_recipients = list(set(_normalize_phone(p) for p in phone_numbers if p))
    if not normalized_recipients:
        return {"success": False, "error": "No valid recipient phone numbers provided.", "count": 0}

    if africastalking and AFRICASTALKING_LIVE_API_KEY:
        try:
            sms_client = getattr(africastalking, "SMS", None)
            if sms_client and hasattr(sms_client, "send"):
                kwargs = {"message": message, "recipients": normalized_recipients}
                if sender_id:
                    kwargs["sender_id"] = sender_id
                response = sms_client.send(**kwargs)
                logger.info("Africa's Talking SMS response: %s", response)
                return {"success": True, "response": response, "count": len(normalized_recipients)}
        except Exception as exc:
            logger.error("Africa's Talking SDK SMS error: %s", exc)

    # REST Fallback
    try:
        url = "https://api.africastalking.com/version1/messaging"
        payload_data = {
            "username": AFRICASTALKING_LIVE_USERNAME,
            "to": ",".join(normalized_recipients),
            "message": message,
        }
        if sender_id:
            payload_data["from"] = sender_id

        payload = urllib.parse.urlencode(payload_data).encode("utf-8")
        req = urllib.request.Request(url, data=payload, method="POST")
        req.add_header("Accept", "application/json")
        req.add_header("Content-Type", "application/x-www-form-urlencoded")
        req.add_header("apiKey", AFRICASTALKING_LIVE_API_KEY)

        with urllib.request.urlopen(req, timeout=30) as resp:
            body = resp.read().decode("utf-8")
            return {"success": True, "response": body, "count": len(normalized_recipients)}
    except Exception as exc:
        logger.error("REST SMS Fallback failed: %s", exc)
        return {"success": False, "error": str(exc), "count": len(normalized_recipients)}


# ==========================================
# REST API VIEWS FOR DASHBOARD & MANAGEMENT
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

        plan = Subscription.objects.filter(name=org.subscription_tier).first()
        spaces = Space.objects.filter(organization=org)
        total_spaces = spaces.count()
        total_members = SpaceMember.objects.filter(space__in=spaces).values('phone_number').distinct().count()

        # Broadcasts sent this month
        now = timezone.now()
        start_of_month = datetime(now.year, now.month, 1, tzinfo=now.tzinfo)
        broadcasts_this_month = Broadcast.objects.filter(
            space__in=spaces, status='sent', sent_at__gte=start_of_month
        ).count()

        return Response({
            'organization': org.name,
            'subscription_tier': org.subscription_tier,
            'sms_balance': org.sms_balance,
            'total_spaces': total_spaces,
            'max_spaces_limit': plan.max_spaces if plan else 1,
            'total_members': total_members,
            'max_members_per_space': plan.max_members_per_space if plan else 100,
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

        plan = Subscription.objects.filter(name=org.subscription_tier).first()
        max_allowed = plan.max_spaces if plan else 1

        if org.spaces.count() >= max_allowed:
            raise ValidationError(
                f"Subscription limit reached ({max_allowed} space max for {org.subscription_tier} plan). Upgrade tier to create more spaces."
            )

        serializer.save(
            organization=org,
            host_phone=self.request.user.phone or getattr(settings, "AT_VOICE_NUMBER", "+256323200925")
        )

    @action(detail=True, methods=['post'], url_path='go-live')
    def go_live_api(self, request, pk=None):
        space = self.get_object()
        space.is_active = True
        space.save(update_fields=['is_active'])

        # Trigger best-effort outbound voice calls to members
        members_phones = list(space.members.values_list('phone_number', flat=True))
        if members_phones and AFRICASTALKING_LIVE_API_KEY:
            try:
                payload = urllib.parse.urlencode({
                    "username": AFRICASTALKING_LIVE_USERNAME,
                    "from": AT_VOICE_NUMBER,
                    "to": "[" + ", ".join([_normalize_phone(p) for p in members_phones]) + "]",
                    "clientRequestId": space.pin,
                }).encode("utf-8")
                req = urllib.request.Request(AT_CALL_URL, data=payload, method="POST")
                req.add_header("Accept", "application/json")
                req.add_header("Content-Type", "application/x-www-form-urlencoded")
                req.add_header("apiKey", AFRICASTALKING_LIVE_API_KEY)
                urllib.request.urlopen(req, timeout=10)
            except Exception as exc:
                logger.warning("Outbound call exception for space %s: %s", space.name, exc)

        return Response({
            'message': f"Space '{space.name}' is now LIVE.",
            'pin': space.pin,
            'invited_callers_count': len(members_phones)
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

        plan = Subscription.objects.filter(name=org.subscription_tier).first()
        if not plan or not plan.allow_merge_spaces:
            return Response(
                {'detail': 'Merge spaces feature is available on Pro and Premium subscription tiers.'},
                status=status.HTTP_403_FORBIDDEN
            )

        source_id = serializer.validated_data['source_space_id']
        target_id = serializer.validated_data['target_space_id']

        source_space = Space.objects.filter(id=source_id, organization=org).first()
        target_space = Space.objects.filter(id=target_id, organization=org).first()

        if not source_space or not target_space:
            return Response({'detail': 'One or both spaces were not found.'}, status=status.HTTP_404_NOT_FOUND)

        with transaction.atomic():
            # Move all members from source to target without duplicates
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
        plan = Subscription.objects.filter(name=org.subscription_tier).first() if org else None
        max_allowed = plan.max_members_per_space if plan else 100

        if space.members.count() >= max_allowed:
            raise ValidationError(
                f"Member limit reached ({max_allowed} members max for {org.subscription_tier} plan)."
            )

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

        decoded_file = file_obj.read().decode('utf-8')
        io_string = io.StringIO(decoded_file)
        reader = csv.DictReader(io_string)

        imported_count = 0
        skipped_count = 0

        for row in reader:
            phone = row.get('phone') or row.get('phone_number') or row.get('Phone')
            if not phone:
                continue
            phone = _normalize_phone(phone)
            name = row.get('name') or row.get('Name') or ''
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


class BroadcastViewSet(viewsets.ModelViewSet):
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = BroadcastSerializer

    def get_queryset(self):
        org = Organization.objects.filter(owner=self.request.user).first()
        if org:
            return Broadcast.objects.filter(space__organization=org)
        return Broadcast.objects.none()

    def perform_create(self, serializer):
        space = serializer.validated_data['space']
        org = space.organization
        message = serializer.validated_data['message']
        broadcast_status = serializer.validated_data.get('status', 'draft')

        recipients = list(space.members.values_list('phone_number', flat=True))
        recipients_count = len(recipients)

        if broadcast_status == 'sent':
            if org.sms_balance < recipients_count:
                raise ValidationError(
                    f"Insufficient SMS balance ({org.sms_balance} available, {recipients_count} required)."
                )

            # Send SMS via Africa's Talking
            res = send_bulk_sms(recipients, message, sender_id=org.sender_id)

            # Deduct balance & create log
            org.sms_balance -= recipients_count
            org.save()

            SMSUsageLog.objects.create(
                organization=org,
                recipient_count=recipients_count,
                sms_cost_credits=recipients_count,
                description=f"Broadcast to Space '{space.name}'"
            )

            serializer.save(
                created_by=self.request.user,
                recipients_count=recipients_count,
                cost_credits=recipients_count,
                sent_at=timezone.now(),
                status='sent'
            )
        else:
            serializer.save(
                created_by=self.request.user,
                recipients_count=recipients_count,
                cost_credits=recipients_count,
                status=broadcast_status
            )


class SurveyViewSet(viewsets.ModelViewSet):
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = SurveySerializer

    def get_queryset(self):
        org = Organization.objects.filter(owner=self.request.user).first()
        if org:
            return Survey.objects.filter(space__organization=org)
        return Survey.objects.none()

    def perform_create(self, serializer):
        serializer.save(created_by=self.request.user)

    @action(detail=True, methods=['post'], url_path='add-question')
    def add_question(self, request, pk=None):
        survey = self.get_object()
        q_serializer = SurveyQuestionSerializer(data=request.data)
        if q_serializer.is_valid():
            q_serializer.save(survey=survey)
            return Response(q_serializer.data, status=status.HTTP_201_CREATED)
        return Response(q_serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    @action(detail=True, methods=['get'], url_path='analytics')
    def analytics(self, request, pk=None):
        survey = self.get_object()
        questions = survey.questions.all()
        data = []

        for q in questions:
            responses = q.responses.all()
            total_r = responses.count()
            counts = {}
            for r in responses:
                val = r.answer_value or r.answer_text
                counts[val] = counts.get(val, 0) + 1

            percentages = {k: round((v / total_r) * 100, 2) for k, v in counts.items()} if total_r > 0 else {}

            data.append({
                'question_id': q.id,
                'question_text': q.question_text,
                'question_type': q.question_type,
                'total_responses': total_r,
                'breakdown': counts,
                'percentages': percentages
            })

        return Response({
            'survey_id': survey.id,
            'title': survey.title,
            'space': survey.space.name,
            'questions_analytics': data
        })


# ==========================================
# AFRICA'S TALKING TELEPHONY & USSD CALLBACKS
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

    # Check if caller is an Organization Owner/Admin
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
            recipients = list(space.members.values_list('phone_number', flat=True))
            send_bulk_sms(recipients, msg)
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


@csrf_exempt
def voice_callback(request):
    if request.method != "POST":
        return _xml('<?xml version="1.0" encoding="UTF-8"?><Response><Say>Invalid request method.</Say></Response>')

    session_id = request.POST.get("sessionId", "")
    is_active = request.POST.get("isActive", "1")
    caller_number = request.POST.get("callerNumber") or request.POST.get("phoneNumber") or ""
    dtmf_digits = (request.POST.get("dtmfDigits", "") or request.POST.get("digits", "")).strip()

    if is_active == "0":
        ActiveSpaceParticipant.objects.filter(call_session_id=session_id).delete()
        return _xml('<?xml version="1.0" encoding="UTF-8"?><Response></Response>')

    if not dtmf_digits:
        callback_url = request.build_absolute_uri(request.path)
        return _xml(
            '<?xml version="1.0" encoding="UTF-8"?><Response>'
            '<GetDigits timeout="20" finishOnKey="#" numDigits="4" '
            f'callbackUrl="{sx.escape(callback_url)}">'
            '<Say>Welcome to Yo-Spaces. Enter your 4-digit PIN then press hash.</Say>'
            '</GetDigits>'
            '</Response>'
        )

    space = Space.objects.filter(pin=dtmf_digits).first()
    if not space:
        return _xml('<?xml version="1.0" encoding="UTF-8"?><Response><Say>Invalid Space PIN. Goodbye.</Say></Response>')

    caller = _normalize_phone(caller_number)
    ActiveSpaceParticipant.objects.update_or_create(
        space=space,
        phone_number=caller,
        defaults={"call_session_id": session_id}
    )

    is_host = caller == _normalize_phone(space.host_phone)
    attrs = f'maxParticipants="20" record="false" beep="onEnter" startOnEnter="{"true" if is_host else "false"}"'

    return _xml(
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<Response>'
        f'<Say>Connecting you to {sx.escape(space.name)}</Say>'
        f'<Conference {attrs}>{sx.escape(space.pin)}</Conference>'
        '</Response>'
    )


@csrf_exempt
def conference_control(request):
    if request.method != "POST":
        return JsonResponse({"status": False, "errorMessage": "POST only"}, status=405)

    try:
        payload = json.loads(request.body.decode("utf-8") or "{}")
    except Exception:
        payload = request.POST.dict()

    payload.setdefault("username", AFRICASTALKING_LIVE_USERNAME)
    payload.setdefault("phoneNumber", AT_VOICE_NUMBER)

    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(AT_CONFERENCE_URL, data=data, method="POST")
    req.add_header("Content-Type", "application/json")
    req.add_header("Accept", "application/json")
    req.add_header("apiKey", AFRICASTALKING_LIVE_API_KEY)

    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return HttpResponse(resp.read().decode("utf-8"), content_type="application/json", status=resp.status)
    except Exception as exc:
        return JsonResponse({"status": False, "errorMessage": str(exc)}, status=500)


@csrf_exempt
def active_listeners(request):
    data = [
        {
            "space": p.space.name,
            "phone": p.masked_phone(),
            "joined_at": p.joined_at.isoformat(),
        }
        for p in ActiveSpaceParticipant.objects.select_related("space").filter(space__is_active=True)
    ]
    return JsonResponse({"active": data})


@csrf_exempt
def sms_delivery_report(request):
    """
    Africa's Talking SMS Delivery Report Webhook
    """
    if request.method == "POST":
        msg_id = request.POST.get("id")
        status_text = request.POST.get("status")
        phoneNumber = request.POST.get("phoneNumber")
        logger.info("SMS DLR Received - ID: %s, Phone: %s, Status: %s", msg_id, phoneNumber, status_text)
        return HttpResponse("OK", content_type="text/plain")
    return HttpResponse("DLR Webhook Ready", content_type="text/plain")
