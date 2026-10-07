"""SMS provider integrations and outbound message formatting."""

import logging
import urllib.parse
import urllib.request
from typing import Optional

from django.conf import settings

from .utils import _normalize_phone

logger = logging.getLogger("yospaces")

AFRICASTALKING_USERNAME = getattr(settings, "AFRICASTALKING_LIVE_USERNAME", "yo_space")
AFRICASTALKING_API_KEY = getattr(settings, "AFRICASTALKING_LIVE_API_KEY", "")
SMS_PROVIDER_TIMEOUT = getattr(settings, "SMS_PROVIDER_TIMEOUT", 30)

try:
    import africastalking  # type: ignore
except ImportError:  # pragma: no cover - optional provider SDK
    africastalking = None

if africastalking and AFRICASTALKING_API_KEY:
    try:
        africastalking.initialize(AFRICASTALKING_USERNAME, AFRICASTALKING_API_KEY)
    except Exception:
        logger.exception("Africa's Talking SDK initialization failed")


def format_sms_message(
    message: str,
    *,
    sender_id: Optional[str] = None,
    org_name: Optional[str] = None,
) -> str:
    """Prefix messages with the organization name when no sender ID is set."""
    if org_name and not sender_id and not message.startswith(f"[{org_name}]"):
        return f"[{org_name}]: {message}"
    return message


def send_bulk_sms(
    phone_numbers: list[str],
    message: str,
    sender_id: Optional[str] = None,
    org_name: Optional[str] = None,
) -> dict:
    """Send one message to normalized recipients using Africa's Talking."""
    message = format_sms_message(message, sender_id=sender_id, org_name=org_name)
    recipients = sorted(
        {
            normalized
            for phone in phone_numbers
            if (normalized := _normalize_phone(phone))
        }
    )
    if not recipients:
        return {
            "success": False,
            "error": "No valid recipient phone numbers provided.",
            "count": 0,
        }

    if africastalking and AFRICASTALKING_API_KEY:
        try:
            sms_client = getattr(africastalking, "SMS", None)
            if sms_client and hasattr(sms_client, "send"):
                kwargs = {"message": message, "recipients": recipients}
                if sender_id:
                    kwargs["sender_id"] = sender_id
                response = sms_client.send(**kwargs)
                logger.info("Africa's Talking accepted SMS for %d recipients", len(recipients))
                return {"success": True, "response": response, "count": len(recipients)}
        except Exception:
            logger.exception("Africa's Talking SDK SMS request failed; using REST fallback")

    return _send_with_rest_api(recipients, message, sender_id)


def _send_with_rest_api(
    recipients: list[str], message: str, sender_id: Optional[str]
) -> dict:
    """Send through the provider's form-encoded REST endpoint."""
    payload_data = {
        "username": AFRICASTALKING_USERNAME,
        "to": ",".join(recipients),
        "message": message,
    }
    if sender_id:
        payload_data["from"] = sender_id

    request = urllib.request.Request(
        "https://api.africastalking.com/version1/messaging",
        data=urllib.parse.urlencode(payload_data).encode("utf-8"),
        method="POST",
    )
    request.add_header("Accept", "application/json")
    request.add_header("Content-Type", "application/x-www-form-urlencoded")
    request.add_header("apiKey", AFRICASTALKING_API_KEY)

    try:
        with urllib.request.urlopen(request, timeout=SMS_PROVIDER_TIMEOUT) as response:
            body = response.read().decode("utf-8")
        return {"success": True, "response": body, "count": len(recipients)}
    except Exception as exc:
        logger.exception("Africa's Talking REST SMS request failed")
        return {"success": False, "error": str(exc), "count": len(recipients)}