from __future__ import annotations

import json
import logging
import os
import re
import urllib.error
import urllib.parse
import urllib.request
from typing import Optional

import xml.sax.saxutils as sx
from django.conf import settings
from django.http import HttpResponse, JsonResponse
from django.views.decorators.csrf import csrf_exempt

from .models import ActiveSpaceParticipant, Space, SpaceInvitee

try:
    import africastalking  # type: ignore
except Exception:  # pragma: no cover - optional during local edits
    africastalking = None

logger = logging.getLogger("yospaces")

# Load configuration from Django settings (which loads from .env)
AT_VOICE_NUMBER = getattr(settings, 'AT_VOICE_NUMBER', "+256323200925")
AFRICASTALKING_LIVE_USERNAME = getattr(settings, 'AFRICASTALKING_LIVE_USERNAME', "yo_space")
AFRICASTALKING_LIVE_API_KEY = getattr(settings, 'AFRICASTALKING_LIVE_API_KEY', "")
AT_CONFERENCE_URL = "https://voice.africastalking.com/conference"
AT_CALL_URL = "https://voice.africastalking.com/call"

if africastalking and AFRICASTALKING_LIVE_API_KEY:
    try:
        africastalking.initialize(AFRICASTALKING_LIVE_USERNAME, AFRICASTALKING_LIVE_API_KEY)
    except Exception as exc:  # pragma: no cover - depends on installed SDK
        logger.warning("Africa's Talking SDK initialization failed: %s", exc)


def _plain(text: str) -> HttpResponse:
    return HttpResponse(text, content_type="text/plain")


def _xml(text: str) -> HttpResponse:
    return HttpResponse(text, content_type="text/xml")


# Session state tracking for USSD flow
# In production, use Django cache or database-backed sessions
_ussd_sessions = {}


def _get_session(phone_number: str) -> dict:
    """Get or create USSD session for a phone number."""
    if phone_number not in _ussd_sessions:
        _ussd_sessions[phone_number] = {
            "state": "main_menu",
            "space_name": None,
            "step": 0,
        }
    return _ussd_sessions[phone_number]


def _update_session(phone_number: str, **kwargs) -> None:
    """Update USSD session state."""
    session = _get_session(phone_number)
    session.update(kwargs)


def _clear_session(phone_number: str) -> None:
    """Clear USSD session."""
    if phone_number in _ussd_sessions:
        del _ussd_sessions[phone_number]


def _normalize_phone(phone: str) -> str:
    phone = (phone or "").strip().replace(" ", "")
    if not phone:
        return phone
    if phone.startswith("+"):
        return phone
    if phone.startswith("0"):
        return "+256" + phone[1:]
    return "+" + phone


def _sanitize_space_name(name: str) -> str:
    name = (name or "").strip()
    name = re.sub(r"\s+", " ", name)
    name = re.sub(r"[^A-Za-z0-9_ -]", "", name)
    return name[:100] or "YoSpace"


def _current_space_for_host(host_phone: str, space_name: Optional[str] = None) -> Optional[Space]:
    qs = Space.objects.filter(host_phone=_normalize_phone(host_phone))
    if space_name:
        space = qs.filter(name=space_name).first()
        if space:
            return space
    return qs.order_by("-created_at", "-id").first()


def _space_dashboard(space: Space) -> str:
    return (
        f"CON {space.name} Dashboard\n"
        f"PIN: {space.pin}\n"
        "1. Manage Members\n"
        "2. Manage Space\n"
        "3. Go Live"
    )


def _space_members_menu() -> str:
    return (
        "CON Manage Members\n"
        "1. Add Member\n"
        "2. Remove Member\n"
        "3. View Members\n"
        "4. Back"
    )


def _space_manage_menu(space: Space) -> str:
    return (
        f"CON {space.name}\n"
        "1. Edit Space Name\n"
        "2. Go Live\n"
        "3. Back"
    )


def _browse_menu() -> str:
    spaces = _active_spaces()
    if not spaces:
        return "END No active spaces right now."

    lines = ["CON Browse Spaces"]
    for idx, space in enumerate(spaces, start=1):
        lines.append(f"{idx}. {space.name}")
    lines.append("Reply with the number")
    return "\n".join(lines)


def _active_spaces(limit: int = 5):
    return list(Space.objects.filter(is_active=True).order_by("-created_at", "-id")[:limit])


def _members_text(space: Space) -> str:
    numbers = list(space.invitees.values_list("phone_number", flat=True)[:20])
    if not numbers:
        return "END No members added yet."
    return "END Members:\n" + "\n".join(numbers)


def _send_invite_sms(phone_number: str, space: Space) -> None:
    message = (
        f"You've been invited to '{space.name}' on YoSpaces. "
        f"Your room PIN is {space.pin}."
    )
    phone_number = _normalize_phone(phone_number)

    if not africastalking:
        logger.warning("AfricasTalking SDK not installed; skipping SMS to %s", phone_number)
        return

    try:
        sms_client = getattr(africastalking, "SMS", None)
        send_fn = getattr(sms_client, "send", None)
        if callable(send_fn):
            send_fn(message, [phone_number])
        else:
            logger.warning("AfricasTalking SMS client unavailable; skipping SMS to %s", phone_number)
    except Exception as exc:  # pragma: no cover - external network
        logger.error("SMS failed for %s: %s", phone_number, exc)


def _call_invitees(space: Space) -> None:
    """Best-effort outbound calls. The room still works without this."""
    participants = []
    for invitee in space.invitees.all():
        phone = _normalize_phone(invitee.phone_number)
        if phone and phone not in participants:
            participants.append(phone)

    if not participants:
        return

    # Reuse the room PIN as the clientRequestId. AT echoes it back on the
    # call's voice callback, which is what lets voice_callback() recognize
    # these are go-live calls and drop the recipient straight into the
    # conference instead of prompting them for a PIN.
    client_request_id = space.pin

    try:
        if africastalking:
            voice_client = getattr(africastalking, "Voice", None)
            call_fn = getattr(voice_client, "call", None)
            if callable(call_fn):
                try:
                    call_fn(AT_VOICE_NUMBER, participants, client_request_id)
                    logger.info("SDK call placed for %s", space.name)
                    return
                except TypeError:
                    try:
                        call_fn(AT_VOICE_NUMBER, participants)
                        logger.info(
                            "SDK call placed for %s (installed SDK does not accept clientRequestId; "
                            "recipients will be prompted for the PIN instead of auto-joining)",
                            space.name,
                        )
                        return
                    except TypeError:
                        pass
    except Exception as exc:
        logger.warning("SDK voice call failed for %s: %s", space.name, exc)

    if not AFRICASTALKING_LIVE_API_KEY:
        logger.warning("Missing Africa's Talking API key; skipping outbound calls for %s", space.name)
        return

    payload = urllib.parse.urlencode(
        {
            "username": AFRICASTALKING_LIVE_USERNAME,
            "from": AT_VOICE_NUMBER,
            "to": ",".join(participants),
            "clientRequestId": client_request_id,
        }
    ).encode("utf-8")

    req = urllib.request.Request(AT_CALL_URL, data=payload, method="POST")
    req.add_header("Accept", "application/json")
    req.add_header("Content-Type", "application/x-www-form-urlencoded")
    req.add_header("apiKey", AFRICASTALKING_LIVE_API_KEY)

    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            logger.info(
                "Voice call API response for %s: %s",
                space.name,
                resp.read().decode("utf-8", errors="ignore"),
            )
    except Exception as exc:  # pragma: no cover - external network
        logger.error("Call failed for %s: %s", space.name, exc)


def _conference_xml(space: Space, caller_number: str, greeting: str) -> str:
    is_host = _normalize_phone(caller_number) == _normalize_phone(space.host_phone)
    attrs = [
        'maxParticipants="20"',
        'record="false"',
        'beep="onEnter"',
        f'startOnEnter="{"true" if is_host else "false"}"',
        f'endOnExit="{"true" if is_host else "false"}"',
        'muted="false"',
    ]
    if is_host:
        attrs.append('flags="moderator"')

    return (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<Response>'
        f'<Say>{sx.escape(greeting)}</Say>'
        f'<Conference {" ".join(attrs)}>{sx.escape(space.pin)}</Conference>'
        '</Response>'
    )


def go_live(space_name: str, host_phone: str) -> str:
    try:
        space = Space.objects.get(name=space_name, host_phone=_normalize_phone(host_phone))
    except Space.DoesNotExist:
        return "END Space not found."

    if not space.is_active:
        space.is_active = True
        space.save(update_fields=["is_active"])

    try:
        _call_invitees(space)
    except Exception as exc:  # pragma: no cover - keep room live even if outbound calls fail
        logger.exception("Outbound calls failed for %s: %s", space.name, exc)

    return (
        f"END {space.name} is now LIVE.\n"
        f"Room PIN: {space.pin}\n"
        "Participants can dial in and enter the PIN to join."
    )


@csrf_exempt
def ussd_callback(request):
    if request.method != "POST":
        return _plain("END Invalid request method.")

    phone_number = _normalize_phone(request.POST.get("phoneNumber", ""))
    text = (request.POST.get("text", "") or "").strip()
    parts = text.split("*") if text else []

    session = _get_session(phone_number)

    # Handle main menu
    if text == "":
        _update_session(phone_number, state="main_menu", space_name=None, step=0)
        return _plain(
            "CON Welcome to YoSpaces\n"
            "1. Host a Space\n"
            "2. Join a Space\n"
            "3. Browse Spaces\n"
            "4. About YoSpaces\n"
            "5. Exit"
        )

    # Handle "Host a Space" flow
    if text == "1":
        _update_session(phone_number, state="host_space_name", step=1)
        return _plain("CON Enter a name for your Space")

    if session["state"] == "host_space_name" and len(parts) == 1:
        space_name = _sanitize_space_name(parts[0])
        space, _created = Space.objects.get_or_create(
            name=space_name,
            host_phone=phone_number,
        )
        _update_session(phone_number, state="space_dashboard", space_name=space.name, step=2)
        return _plain(_space_dashboard(space))

    # Handle space dashboard options
    if session["state"] == "space_dashboard" and len(parts) == 1:
        space = _current_space_for_host(phone_number, session.get("space_name"))
        if not space:
            _clear_session(phone_number)
            return _plain("END Space not found. Please start over.")

        if parts[0] == "1":  # Manage Members
            _update_session(phone_number, state="manage_members", step=3)
            return _plain(_space_members_menu())

        if parts[0] == "2":  # Manage Space
            _update_session(phone_number, state="manage_space", step=3)
            return _plain(_space_manage_menu(space))

        if parts[0] == "3":  # Go Live
            return _plain(go_live(space.name, phone_number))

    # Handle Manage Members submenu
    if session["state"] == "manage_members" and len(parts) == 1:
        space = _current_space_for_host(phone_number, session.get("space_name"))
        if not space:
            _clear_session(phone_number)
            return _plain("END Space not found. Please start over.")

        if parts[0] == "1":  # Add Member
            _update_session(phone_number, state="add_member_phone", step=4)
            return _plain("CON Enter member phone number")

        if parts[0] == "2":  # Remove Member
            _update_session(phone_number, state="remove_member_phone", step=4)
            return _plain("CON Enter member phone number to remove")

        if parts[0] == "3":  # View Members
            return _plain(_members_text(space))

        if parts[0] == "4":  # Back
            _update_session(phone_number, state="space_dashboard", step=2)
            return _plain(_space_dashboard(space))

    # Handle Add Member phone input
    if session["state"] == "add_member_phone" and len(parts) == 1:
        space = _current_space_for_host(phone_number, session.get("space_name"))
        if not space:
            _clear_session(phone_number)
            return _plain("END Space not found. Please start over.")

        member_phone = _normalize_phone(parts[0])
        _, created = SpaceInvitee.objects.get_or_create(
            space=space,
            phone_number=member_phone,
        )
        if not created:
            _update_session(phone_number, state="manage_members", step=3)
            return _plain("END That number is already invited.")

        _send_invite_sms(member_phone, space)
        _update_session(phone_number, state="manage_members", step=3)
        return _plain(f"END {member_phone} invited to {space.name}.")

    # Handle Remove Member phone input
    if session["state"] == "remove_member_phone" and len(parts) == 1:
        space = _current_space_for_host(phone_number, session.get("space_name"))
        if not space:
            _clear_session(phone_number)
            return _plain("END Space not found. Please start over.")

        member_phone = _normalize_phone(parts[0])
        deleted, _ = SpaceInvitee.objects.filter(space=space, phone_number=member_phone).delete()
        _update_session(phone_number, state="manage_members", step=3)
        return _plain("END Member removed." if deleted else "END Member not found in this space.")

    # Handle Manage Space submenu
    if session["state"] == "manage_space" and len(parts) == 1:
        space = _current_space_for_host(phone_number, session.get("space_name"))
        if not space:
            _clear_session(phone_number)
            return _plain("END Space not found. Please start over.")

        if parts[0] == "1":  # Edit Space Name
            _update_session(phone_number, state="edit_space_name", step=4)
            return _plain("CON Enter the new Space name")

        if parts[0] == "2":  # Go Live
            return _plain(go_live(space.name, phone_number))

        if parts[0] == "3":  # Back
            _update_session(phone_number, state="space_dashboard", step=2)
            return _plain(_space_dashboard(space))

    # Handle Edit Space Name input
    if session["state"] == "edit_space_name" and len(parts) == 1:
        space = _current_space_for_host(phone_number, session.get("space_name"))
        if not space:
            _clear_session(phone_number)
            return _plain("END Space not found. Please start over.")

        new_name = _sanitize_space_name(parts[0])
        if Space.objects.filter(name=new_name, host_phone=phone_number).exclude(pk=space.pk).exists():
            _update_session(phone_number, state="manage_space", step=3)
            return _plain("END That space name already exists.")

        space.name = new_name
        space.save(update_fields=["name"])
        _update_session(phone_number, state="space_dashboard", space_name=new_name, step=2)
        return _plain(_space_dashboard(space))

    # Handle "Join a Space" flow
    if text == "2":
        _update_session(phone_number, state="join_space_pin", step=1)
        return _plain("CON Enter Space PIN")

    if session["state"] == "join_space_pin" and len(parts) == 1:
        pin = parts[0].strip()
        try:
            space = Space.objects.get(pin=pin)
        except Space.DoesNotExist:
            _update_session(phone_number, state="join_space_pin", step=1)
            return _plain("END Invalid Space PIN. Please try again.")

        if _normalize_phone(space.host_phone) == phone_number:
            _update_session(phone_number, state="space_dashboard", space_name=space.name, step=2)
            return _plain(_space_dashboard(space))

        SpaceInvitee.objects.get_or_create(
            space=space,
            phone_number=phone_number,
        )
        _clear_session(phone_number)
        return _plain(
            f"END You are registered for {space.name}.\n"
            f"Dial the voice line and enter PIN {space.pin} to join."
        )

    # Handle "Browse Spaces" flow
    if text == "3":
        _update_session(phone_number, state="browse_spaces", step=1)
        return _plain(_browse_menu())

    if session["state"] == "browse_spaces" and len(parts) == 1:
        spaces = _active_spaces()
        try:
            index = int(parts[0]) - 1
            space = spaces[index]
        except (ValueError, IndexError):
            _update_session(phone_number, state="browse_spaces", step=1)
            return _plain("END Invalid option. Please select a valid number.")

        if _normalize_phone(phone_number) == _normalize_phone(space.host_phone):
            _update_session(phone_number, state="space_dashboard", space_name=space.name, step=2)
            return _plain(_space_dashboard(space))

        SpaceInvitee.objects.get_or_create(
            space=space,
            phone_number=_normalize_phone(phone_number),
        )
        _clear_session(phone_number)
        return _plain(
            f"END {space.name}\n"
            f"PIN: {space.pin}\n"
            "Dial the YoSpaces voice number and enter the PIN to join."
        )

    # Handle About and Exit
    if text == "4":
        _clear_session(phone_number)
        return _plain("END YoSpaces is a 2G-first social audio platform built for local communities.")

    if text == "5":
        _clear_session(phone_number)
        return _plain("END Thanks for using YoSpaces.")

    # Invalid option - provide helpful error message based on current state
    state_messages = {
        "main_menu": "END Invalid option. Please select 1-5.",
        "host_space_name": "END Invalid space name. Please try again.",
        "space_dashboard": "END Invalid option. Please select 1-3.",
        "manage_members": "END Invalid option. Please select 1-4.",
        "add_member_phone": "END Invalid phone number. Please enter a valid number.",
        "remove_member_phone": "END Invalid phone number. Please enter a valid number.",
        "manage_space": "END Invalid option. Please select 1-3.",
        "edit_space_name": "END Invalid space name. Please try again.",
        "join_space_pin": "END Invalid PIN. Please enter a 4-digit PIN.",
        "browse_spaces": "END Invalid option. Please select a valid space number.",
    }
    msg = state_messages.get(session["state"], "END Invalid option. Please try again.")
    return _plain(msg)


@csrf_exempt
def voice_callback(request):
    if request.method != "POST":
        return _xml('<?xml version="1.0" encoding="UTF-8"?><Response><Say>Invalid request method.</Say></Response>')

    session_id = request.POST.get("sessionId", "")
    is_active = request.POST.get("isActive", "1")
    caller_number = request.POST.get("callerNumber") or request.POST.get("phoneNumber") or ""
    destination_number = request.POST.get("destinationNumber", "")
    dtmf_digits = (request.POST.get("dtmfDigits", "") or request.POST.get("digits", "")).strip()
    client_request_id = (request.POST.get("clientRequestId", "") or "").strip()

    if is_active == "0":
        ActiveSpaceParticipant.objects.filter(call_session_id=session_id).delete()
        return _xml('<?xml version="1.0" encoding="UTF-8"?><Response></Response>')

    if client_request_id:
        try:
            space = Space.objects.get(pin=client_request_id)
        except Space.DoesNotExist:
            space = None
        if space:
            ActiveSpaceParticipant.objects.update_or_create(
                space=space,
                phone_number=_normalize_phone(caller_number or destination_number),
                defaults={"call_session_id": session_id},
            )
            return _xml(_conference_xml(space, caller_number, f"Connecting you to {space.name}"))

    if not dtmf_digits:
        callback_url = request.build_absolute_uri(request.path)
        xml = (
            '<?xml version="1.0" encoding="UTF-8"?><Response>'
            '<GetDigits timeout="20" finishOnKey="#" numDigits="4" '
            f'callbackUrl="{sx.escape(callback_url)}">'
            '<Say>Welcome to YoSpaces. Enter your room PIN then press hash.</Say>'
            '</GetDigits>'
            '</Response>'
        )
        return _xml(xml)

    try:
        space = Space.objects.get(pin=dtmf_digits)
    except Space.DoesNotExist:
        return _xml('<?xml version="1.0" encoding="UTF-8"?><Response><Say>Invalid PIN. Goodbye.</Say></Response>')

    caller_number = _normalize_phone(caller_number or destination_number)

    if caller_number == _normalize_phone(space.host_phone):
        if not space.is_active:
            space.is_active = True
            space.save(update_fields=["is_active"])
    elif not space.is_active:
        return _xml(
            '<?xml version="1.0" encoding="UTF-8"?><Response>'
            '<Say>This room is not live yet. Please try again later.</Say>'
            '</Response>'
        )

    ActiveSpaceParticipant.objects.update_or_create(
        space=space,
        phone_number=caller_number,
        defaults={"call_session_id": session_id},
    )
    return _xml(_conference_xml(space, caller_number, f"Joining {space.name}"))


@csrf_exempt
def conference_control(request):
    if request.method != "POST":
        return JsonResponse({"status": False, "errorMessage": "POST only"}, status=405)

    try:
        payload = json.loads(request.body.decode("utf-8") or "{}")
    except Exception:
        payload = request.POST.dict()

    if not AFRICASTALKING_LIVE_USERNAME or not AFRICASTALKING_LIVE_API_KEY:
        return JsonResponse(
            {"status": False, "errorMessage": "Missing Africa's Talking credentials"},
            status=500,
        )

    payload.setdefault("username", AFRICASTALKING_LIVE_USERNAME)
    payload.setdefault("phoneNumber", AT_VOICE_NUMBER)

    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(AT_CONFERENCE_URL, data=data, method="POST")
    req.add_header("Content-Type", "application/json")
    req.add_header("Accept", "application/json")
    req.add_header("apiKey", AFRICASTALKING_LIVE_API_KEY)

    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            body = resp.read().decode("utf-8")
            return HttpResponse(
                body,
                content_type=resp.headers.get_content_type() or "application/json",
                status=resp.status,
            )
    except urllib.error.HTTPError as exc:
        return JsonResponse(
            {"status": False, "errorMessage": exc.read().decode("utf-8", errors="ignore")},
            status=exc.code,
        )
    except Exception as exc:  # pragma: no cover - external network
        logger.error("Conference API error: %s", exc)
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