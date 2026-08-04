import json
import logging
import urllib.parse
import urllib.request
import xml.sax.saxutils as sx

from django.conf import settings
from django.http import HttpResponse, JsonResponse
from django.views.decorators.csrf import csrf_exempt

from spaces.models import Space, ActiveSpaceParticipant

logger = logging.getLogger("yospaces")

AT_VOICE_NUMBER = getattr(settings, "AT_VOICE_NUMBER", "+256323200925")
AFRICASTALKING_LIVE_USERNAME = getattr(settings, "AFRICASTALKING_LIVE_USERNAME", "yo_space")
AFRICASTALKING_LIVE_API_KEY = getattr(settings, "AFRICASTALKING_LIVE_API_KEY", "")
AT_CONFERENCE_URL = "https://voice.africastalking.com/conference"
AT_CALL_URL = "https://voice.africastalking.com/call"


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


def trigger_outbound_space_calls(space) -> int:
    """
    Triggers outbound Africa's Talking voice calls to members of a Space.
    """
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
    return len(members_phones)


@csrf_exempt
def voice_callback(request):
    """
    Africa's Talking Voice Call Interactive Callback XML Handler.
    Prompts for 4-digit PIN and joins callers to conference room.
    """
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
    """
    Relays Conference Control requests (mute, kick, hold) to Africa's Talking Voice API.
    """
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
    """
    Returns active voice call participants per space.
    """
    data = [
        {
            "space": p.space.name,
            "phone": p.masked_phone(),
            "joined_at": p.joined_at.isoformat(),
        }
        for p in ActiveSpaceParticipant.objects.select_related("space").filter(space__is_active=True)
    ]
    return JsonResponse({"active": data})
