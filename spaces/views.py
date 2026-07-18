# # from django.http import HttpResponse, JsonResponse
# # from django.views.decorators.csrf import csrf_exempt
# # import xml.sax.saxutils as sx
# # import logging
# # from .models import *
# # import africastalking

# # logger = logging.getLogger("yospaces")

# # # Configure AfricasTalking credentials

# # # Configure Gemini Credentials

# # @csrf_exempt
# # def ussd_callback(request):
# #     session_id = request.POST.get("sessionId", "")
# #     service_code = request.POST.get("serviceCode", "")
# #     phone_number = request.POST.get("phoneNumber", "")
# #     text = request.POST.get("text", "")

# #     input_parts = text.split("*") if text else []

# #     # ==========================
# #     # MAIN MENU
# #     # ==========================
# #     if text == "":
# #         response = "CON Welcome to YoSpaces\n"
# #         response += "1. Host a Space\n"
# #         response += "2. Join a Space\n"
# #         response += "3. Browse Spaces\n"
# #         response += "4. About YoSpaces\n"
# #         response += "5. Exit"
        

# #     # ==========================
# #     # HOST SPACE
# #     # ==========================
# #     elif text == "1":
# #         response = "CON Enter a name for your Space"

# #     elif len(input_parts) == 2 and input_parts[0] == "1":
# #         space_name = input_parts[1]

# #         space, created = Space.objects.get_or_create(
# #             name=space_name,
# #             host_phone=phone_number
# #         )

# #         response = f"CON {space.name} Dashboard\n"
# #         response += "1. Manage Members\n"
# #         response += "2. Manage Space\n"
# #         response += "3. Go Live"
        

# #     # ==========================
# #     # MANAGE MEMBERS
# #     # ==========================
# #     elif len(input_parts) == 3 and input_parts[0] == "1" and input_parts[2] == "1":

# #         response = "CON Manage Members\n"
# #         response += "1. Add Member\n"
# #         response += "2. Remove Member\n"
# #         response += "3. View Members"

# #     # ==========================
# #     # MANAGE SPACE
# #     # ==========================
# #     elif len(input_parts) == 3 and input_parts[0] == "1" and input_parts[2] == "2":

# #         try:
# #             space = Space.objects.filter(
# #                 host_phone=phone_number
# #             ).latest("id")

# #             response =  f"CON {space.name}\n"
# #             response += "1. Edit Space\n"
# #             response += "2. Go Live"
            

# #         except Space.DoesNotExist:
# #             response = "END No active space found."

# #     # ==========================
# #     # GO LIVE
# #     # ==========================
# #     elif len(input_parts) == 3 and input_parts[0] == "1" and input_parts[2] == "3":

# #         response =  "END Space is Live!\n Participants will receive calls shortly."
      

# #     # ==========================
# #     # JOIN SPACE
# #     # ==========================
# #     elif text == "2":
# #         response = "CON Enter Space PIN"

# #     elif len(input_parts) == 2 and input_parts[0] == "2":

# #         pin = input_parts[1]

# #         try:
# #             space = Space.objects.get(pin=pin)

# #             response =  f"END Joined {space.name} successfully!"

# #         except Space.DoesNotExist:
# #             response = "END Invalid Space PIN."

# #     # ==========================
# #     # BROWSE
# #     # ==========================
# #     elif text == "3":
# #         response = "END Browse Spaces coming soon."

# #     # ==========================
# #     # ABOUT
# #     # ==========================
# #     elif text == "4":
# #         response =  "END YoSpaces is a 2G-first social audio platform built for local communities."

# #     # ==========================
# #     # EXIT
# #     # ==========================
# #     elif text == "5":
# #         response = "END Thanks for using YoSpaces."

# #     # ==========================
# #     # INVALID
# #     # ==========================
# #     else:
# #         response = "END Invalid option."

# #     return HttpResponse(response, content_type="text/plain")        


# # def add_member(space_name, host_phone, member_phone):
# #     try:
# #         space = Space.objects.get(name=space_name, host_phone=host_phone)
# #     except Space.DoesNotExist:
# #         return "END Space not found. Please start over."
 
# #     invitee, created = SpaceInvitee.objects.get_or_create(
# #         space=space, phone_number=member_phone
# #     )
# #     if not created:
# #         return "END That number is already invited."
 
# #     send_invite_sms(member_phone, space)
# #     return f"END {member_phone} invited to {space_name}. Dial again to add more or go live."
 
 
# # def remove_member(space_name, member_phone):
# #     deleted, _ = SpaceInvitee.objects.filter(
# #         space__name=space_name, phone_number=member_phone
# #     ).delete()
# #     return "END Member removed." if deleted else "END Member not found in this space."
 
 
# # def view_members(space_name):
# #     try:
# #         space = Space.objects.get(name=space_name)
# #     except Space.DoesNotExist:
# #         return "END Space not found."
 
# #     numbers = list(space.invitees.values_list("phone_number", flat=True)[:8])
# #     if not numbers:
# #         return "END No members added yet."
# #     return "END Members:\n" + "\n".join(numbers)
 
 
# # def go_live(space_name, host_phone):
# #     try:
# #         space = Space.objects.get(name=space_name, host_phone=host_phone)
# #     except Space.DoesNotExist:
# #         return "END Space not found. Please start over."
 
# #     if not space.is_active:
# #         space.is_active = True
# #         space.save(update_fields=["is_active"])
 
# #     call_invitees(space)
# #     return f"END {space.name} is live! Your PIN is {space.pin}. We're calling your invitees now."

 
# # def format_phone(phone):
# #     phone = phone.strip()
# #     if phone.startswith("0"):
# #         return "+256" + phone[1:]
# #     return phone if phone.startswith("+") else "+" + phone
 
# # def call_invitees(space):
# #     for invitee in space.invitees.all():
# #         try:
# #             africastalking.Voice.call({
# #                 "callFrom": settings.AT_VOICE_NUMBER,
# #                 "callTo": [format_phone(invitee.phone_number)],
# #                 "clientRequestId": space.pin,
# #             })
# #         except Exception as e:
# #             logger.error("Call failed for %s: %s", invitee.phone_number, e)
 
# # def send_invite_sms(phone_number, space):
# #     message = f"You've been invited to '{space.name}' on YoSpaces. We'll call you shortly to connect you."
# #     try:
# #         africastalking.SMS.send(message, [format_phone(phone_number)])
# #     except Exception as e:
# #         logger.error("SMS failed for %s: %s", phone_number, e)
 
# # def conference_xml(space, caller_number, greeting):
# #     is_host = caller_number == space.host_phone
# #     return (
# #         f'<?xml version="1.0" encoding="UTF-8"?><Response>'
# #         f'<Say>{sx.escape(greeting)}</Say>'
# #         f'<Conference maxParticipants="20" beep="onEnter" '
# #         f'startOnEnter="{"true" if is_host else "false"}" '
# #         f'endOnExit="{"true" if is_host else "false"}" '
# #         f'flags="{"moderator" if is_host else ""}">'
# #         f'{space.pin}</Conference></Response>'
# #     )

# # # implement voice support for the application
# # def voice_callback(request):
# #     session_id = request.POST.get("sessionId")
# #     is_active = request.POST.get("isActive")
# #     caller_number = request.POST.get("callerNumber") or request.POST.get("destinationNumber")
# #     dtmf_digits = request.POST.get("dtmfDigits")
# #     client_request_id = request.POST.get("clientRequestId")
# #     if is_active == "0":
# #         ActiveSpaceParticipant.objects.filter(call_session_id=session_id).delete()
# #         return HttpResponse("", content_type="text/plain")
 
# #     if client_request_id:
# #         try:
# #             space = Space.objects.get(pin=client_request_id, is_active=True)
# #             ActiveSpaceParticipant.objects.update_or_create(
# #                 space=space, phone_number=caller_number,
# #                 defaults={"call_session_id": session_id},
# #             )
# #             return HttpResponse(
# #                 conference_xml(space, caller_number, f"Connecting you to {space.name}"),
# #                 content_type="text/xml",
# #             )
# #         except Space.DoesNotExist:
# #             pass
 
# #     if not dtmf_digits:
# #         xml = (
# #             '<?xml version="1.0" encoding="UTF-8"?><Response>'
# #             '<GetDigits timeout="15" finishOnKey="#" callbackUrl="/api/voice-callback/">'
# #             '<Say>Welcome to YoSpaces. Enter your room PIN then press hash.</Say>'
# #             '</GetDigits></Response>'
# #         )
# #         return HttpResponse(xml, content_type="text/xml")
 
# #     try:
# #         space = Space.objects.get(pin=dtmf_digits, is_active=True)
# #         ActiveSpaceParticipant.objects.update_or_create(
# #             space=space, phone_number=caller_number,
# #             defaults={"call_session_id": session_id},
# #         )
# #         xml = conference_xml(space, caller_number, f"Joining {space.name}")
# #     except Space.DoesNotExist:
# #         xml = '<?xml version="1.0" encoding="UTF-8"?><Response><Say>Invalid PIN. Goodbye.</Say></Response>'
 
# #     return HttpResponse(xml, content_type="text/xml")
 
 
# # def active_listeners(request):
# #     data = [
# #         {"space": p.space.name, "phone": p.masked_phone(), "joined_at": p.joined_at.isoformat()}
# #         for p in ActiveSpaceParticipant.objects.select_related("space").filter(space__is_active=True)
# #     ]
# #     return JsonResponse({"active": data})
 
# from __future__ import annotations

# import base64
# import json
# import logging
# import os
# import re
# import urllib.error
# import urllib.request
# from typing import Optional

# import xml.sax.saxutils as sx
# from django.conf import settings
# from django.http import HttpResponse, JsonResponse
# from django.views.decorators.csrf import csrf_exempt

# from .models import ActiveSpaceParticipant, Space, SpaceInvitee

# try:
#     import africastalking  # type: ignore
# except Exception:  # pragma: no cover - optional during local edits
#     africastalking = None

# logger = logging.getLogger("yospaces")

# AT_VOICE_NUMBER = "+256323200925"
# AFRICASTALKING_LIVE_USERNAME = "yo_space"
# AFRICASTALKING_LIVE_API_KEY = "atsk_d0ad900cfea42fa2fca26ee5bc47964c8e1e092d5565e4c0ce5217a82c5267ed079ab373"
# AT_CONFERENCE_URL = getattr(
#     settings,
#     "AT_CONFERENCE_URL",
#     os.getenv("AT_CONFERENCE_URL", "https://voice.africastalking.com/conference"),
# )


# def _plain(text: str) -> HttpResponse:
#     return HttpResponse(text, content_type="text/plain")


# def _xml(text: str) -> HttpResponse:
#     return HttpResponse(text, content_type="text/xml")


# def _normalize_phone(phone: str) -> str:
#     phone = (phone or "").strip()
#     if not phone:
#         return phone
#     if phone.startswith("+"):
#         return phone
#     if phone.startswith("0"):
#         return "+256" + phone[1:]
#     return "+" + phone


# def _sanitize_space_name(name: str) -> str:
#     name = (name or "").strip()
#     name = re.sub(r"\s+", " ", name)
#     name = re.sub(r"[^A-Za-z0-9_ -]", "", name)
#     return name[:100] or "YoSpace"


# def _latest_host_space(host_phone: str) -> Optional[Space]:
#     return (
#         Space.objects.filter(host_phone=host_phone)
#         .order_by("-created_at", "-id")
#         .first()
#     )


# def _current_space_for_host(host_phone: str, space_name: Optional[str] = None) -> Optional[Space]:
#     qs = Space.objects.filter(host_phone=host_phone)
#     if space_name:
#         space = qs.filter(name=space_name).first()
#         if space:
#             return space
#     return qs.order_by("-created_at", "-id").first()


# def _space_dashboard(space: Space) -> str:
#     return (
#         f"CON {space.name} Dashboard\n"
#         f"PIN: {space.pin}\n"
#         "1. Manage Members\n"
#         "2. Manage Space\n"
#         "3. Go Live"
#     )


# def _space_members_menu() -> str:
#     return (
#         "CON Manage Members\n"
#         "1. Add Member\n"
#         "2. Remove Member\n"
#         "3. View Members\n"
#         "4. Back"
#     )


# def _space_manage_menu(space: Space) -> str:
#     return (
#         f"CON {space.name}\n"
#         "1. Edit Space Name\n"
#         "2. Go Live\n"
#         "3. Back"
#     )


# def _members_text(space: Space) -> str:
#     numbers = list(space.invitees.values_list("phone_number", flat=True)[:20])
#     if not numbers:
#         return "END No members added yet."
#     return "END Members:\n" + "\n".join(numbers)


# def _send_invite_sms(phone_number: str, space: Space) -> None:
#     message = (
#         f"You've been invited to '{space.name}' on YoSpaces. "
#         f"Your room PIN is {space.pin}."
#     )
#     phone_number = _normalize_phone(phone_number)

#     if not africastalking:
#         logger.warning("AfricasTalking SDK not installed; skipping SMS to %s", phone_number)
#         return

#     try:
#         if hasattr(africastalking, "SMS") and hasattr(africastalking.SMS, "send"):
#             africastalking.SMS.send(message, [phone_number])
#         else:
#             logger.warning("AfricasTalking SMS client unavailable; skipping SMS to %s", phone_number)
#     except Exception as exc:  # pragma: no cover - external network
#         logger.error("SMS failed for %s: %s", phone_number, exc)


# def _call_invitees(space: Space) -> None:
#     if not africastalking:
#         logger.warning("AfricasTalking SDK not installed; skipping outbound calls for %s", space.name)
#         return

#     if not AT_VOICE_NUMBER or not AFRICASTALKING_LIVE_USERNAME or not AFRICASTALKING_LIVE_API_KEY:
#         logger.warning(
#             "Missing AT voice credentials; skipping outbound calls for space %s", space.name
#         )
#         return

#     voice_client = getattr(africastalking, "Voice", None)
#     call_fn = getattr(voice_client, "call", None)
#     if not callable(call_fn):
#         logger.warning("AfricasTalking Voice client unavailable; skipping outbound calls")
#         return

#     for invitee in space.invitees.all():
#         phone = _normalize_phone(invitee.phone_number)
#         payload = {
#             "callFrom": AT_VOICE_NUMBER,
#             "callTo": [phone],
#             # clientRequestId is echoed back on the voice callback so we can join the room.
#             "clientRequestId": space.pin,
#         }
#         try:
#             call_fn(payload)
#             logger.info("Placed voice call to %s for space %s", phone, space.name)
#         except Exception as exc:  # pragma: no cover - external network
#             logger.error("Call failed for %s: %s", phone, exc)


# def _conference_xml(space: Space, caller_number: str, greeting: str) -> str:
#     is_host = _normalize_phone(caller_number) == _normalize_phone(space.host_phone)
#     attrs = [
#         'maxParticipants="20"',
#         'record="false"',
#         'beep="onEnter"',
#         f'startOnEnter="{"true" if is_host else "false"}"',
#         f'endOnExit="{"true" if is_host else "false"}"',
#         'muted="false"',
#         'flags="moderator"' if is_host else '',
#     ]
#     attrs = [a for a in attrs if a]
#     return (
#         '<?xml version="1.0" encoding="UTF-8"?>'
#         '<Response>'
#         f'<Say>{sx.escape(greeting)}</Say>'
#         f'<Conference {" ".join(attrs)}>{sx.escape(space.pin)}</Conference>'
#         '</Response>'
#     )


# @csrf_exempt
# def ussd_callback(request):
#     if request.method != "POST":
#         return _plain("END Invalid request method.")

#     phone_number = request.POST.get("phoneNumber", "")
#     text = (request.POST.get("text", "") or "").strip()
#     parts = text.split("*") if text else []

#     # Main menu
#     if text == "":
#         return _plain(
#             "CON Welcome to YoSpaces\n"
#             "1. Host a Space\n"
#             "2. Join a Space\n"
#             "3. Browse Spaces\n"
#             "4. About YoSpaces\n"
#             "5. Exit"
#         )

#     # Host flow
#     if text == "1":
#         return _plain("CON Enter a name for your Space")

#     if len(parts) == 2 and parts[0] == "1":
#         space_name = _sanitize_space_name(parts[1])
#         space, _created = Space.objects.get_or_create(
#             name=space_name,
#             host_phone=phone_number,
#         )
#         return _plain(_space_dashboard(space))

#     # Manage members menu
#     if len(parts) == 3 and parts[0] == "1" and parts[2] == "1":
#         return _plain(_space_members_menu())

#     # Add member
#     if len(parts) == 4 and parts[0] == "1" and parts[2] == "1" and parts[3] == "1":
#         return _plain("CON Enter member phone number")

#     if len(parts) == 5 and parts[0] == "1" and parts[2] == "1" and parts[3] == "1":
#         space = _current_space_for_host(phone_number, parts[1])
#         if not space:
#             return _plain("END Space not found. Please start over.")

#         member_phone = _normalize_phone(parts[4])
#         invitee, created = SpaceInvitee.objects.get_or_create(
#             space=space,
#             phone_number=member_phone,
#         )
#         if not created:
#             return _plain("END That number is already invited.")

#         _send_invite_sms(member_phone, space)
#         return _plain(
#             f"END {member_phone} invited to {space.name}."
#         )

#     # Remove member
#     if len(parts) == 4 and parts[0] == "1" and parts[2] == "1" and parts[3] == "2":
#         return _plain("CON Enter member phone number to remove")

#     if len(parts) == 5 and parts[0] == "1" and parts[2] == "1" and parts[3] == "2":
#         space = _current_space_for_host(phone_number, parts[1])
#         if not space:
#             return _plain("END Space not found. Please start over.")

#         member_phone = _normalize_phone(parts[4])
#         deleted, _ = SpaceInvitee.objects.filter(space=space, phone_number=member_phone).delete()
#         return _plain("END Member removed." if deleted else "END Member not found in this space.")

#     # View members
#     if len(parts) == 4 and parts[0] == "1" and parts[2] == "1" and parts[3] == "3":
#         space = _current_space_for_host(phone_number, parts[1])
#         if not space:
#             return _plain("END Space not found. Please start over.")
#         return _plain(_members_text(space))

#     if len(parts) == 4 and parts[0] == "1" and parts[2] == "1" and parts[3] == "4":
#         space = _current_space_for_host(phone_number, parts[1])
#         if not space:
#             return _plain("END Space not found. Please start over.")
#         return _plain(_space_dashboard(space))

#     # Manage space menu
#     if len(parts) == 3 and parts[0] == "1" and parts[2] == "2":
#         space = _current_space_for_host(phone_number, parts[1])
#         if not space:
#             return _plain("END No active space found.")
#         return _plain(_space_manage_menu(space))

#     if len(parts) == 4 and parts[0] == "1" and parts[2] == "2" and parts[3] == "1":
#         return _plain("CON Enter the new Space name")

#     if len(parts) == 5 and parts[0] == "1" and parts[2] == "2" and parts[3] == "1":
#         old_name = _sanitize_space_name(parts[1])
#         new_name = _sanitize_space_name(parts[4])
#         space = _current_space_for_host(phone_number, old_name)
#         if not space:
#             return _plain("END Space not found. Please start over.")
#         if Space.objects.filter(name=new_name, host_phone=phone_number).exclude(pk=space.pk).exists():
#             return _plain("END That space name already exists.")
#         space.name = new_name
#         space.save(update_fields=["name"])
#         return _plain(_space_dashboard(space))

#     if len(parts) == 4 and parts[0] == "1" and parts[2] == "2" and parts[3] == "2":
#         space = _current_space_for_host(phone_number, parts[1])
#         if not space:
#             return _plain("END Space not found. Please start over.")
#         return _plain(go_live(space.name, phone_number))

#     if len(parts) == 4 and parts[0] == "1" and parts[2] == "2" and parts[3] == "3":
#         space = _current_space_for_host(phone_number, parts[1])
#         if not space:
#             return _plain("END Space not found. Please start over.")
#         return _plain(_space_dashboard(space))

#     # Go live from dashboard
#     if len(parts) == 3 and parts[0] == "1" and parts[2] == "3":
#         space = _current_space_for_host(phone_number, parts[1])
#         if not space:
#             return _plain("END Space not found. Please start over.")
#         return _plain(go_live(space.name, phone_number))

#     # Join space flow (register for invite and voice call)
#     if text == "2":
#         return _plain("CON Enter Space PIN")

#     if len(parts) == 2 and parts[0] == "2":
#         pin = parts[1].strip()
#         try:
#             space = Space.objects.get(pin=pin)
#         except Space.DoesNotExist:
#             return _plain("END Invalid Space PIN.")

#         SpaceInvitee.objects.get_or_create(
#             space=space,
#             phone_number=_normalize_phone(phone_number),
#         )
#         return _plain(
#             f"END You are registered for {space.name}."
#         )

#     if text == "3":
#         active_spaces = Space.objects.filter(is_active=True).order_by("-created_at")[:5]
#         if not active_spaces:
#             return _plain("END No active spaces right now.")
#         lines = ["END Active Spaces:"]
#         for space in active_spaces:
#             lines.append(f"{space.name} - PIN {space.pin}")
#         return _plain("\n".join(lines))

#     if text == "4":
#         return _plain(
#             "END YoSpaces is a 2G-first social audio platform built for local communities."
#         )

#     if text == "5":
#         return _plain("END Thanks for using YoSpaces.")

#     return _plain("END Invalid option.")


# @csrf_exempt
# def voice_callback(request):
#     if request.method != "POST":
#         return _xml('<?xml version="1.0" encoding="UTF-8"?><Response><Say>Invalid request method.</Say></Response>')

#     session_id = request.POST.get("sessionId", "")
#     is_active = request.POST.get("isActive", "1")
#     caller_number = request.POST.get("callerNumber") or request.POST.get("phoneNumber") or ""
#     destination_number = request.POST.get("destinationNumber", "")
#     dtmf_digits = (request.POST.get("dtmfDigits", "") or request.POST.get("digits", "")).strip()
#     client_request_id = (request.POST.get("clientRequestId", "") or "").strip()

#     # Call ended: clean up any active participant record.
#     if is_active == "0":
#         ActiveSpaceParticipant.objects.filter(call_session_id=session_id).delete()
#         return _xml('<?xml version="1.0" encoding="UTF-8"?><Response></Response>')

#     # Outbound calls can carry the room PIN through clientRequestId.
#     if client_request_id:
#         try:
#             space = Space.objects.get(pin=client_request_id)
#         except Space.DoesNotExist:
#             space = None
#         if space:
#             ActiveSpaceParticipant.objects.update_or_create(
#                 space=space,
#                 phone_number=_normalize_phone(caller_number or destination_number),
#                 defaults={"call_session_id": session_id},
#             )
#             return _xml(_conference_xml(space, caller_number, f"Connecting you to {space.name}"))

#     # First inbound response: ask for the PIN.
#     if not dtmf_digits:
#         callback_url = request.build_absolute_uri(request.path)
#         xml = (
#             '<?xml version="1.0" encoding="UTF-8"?><Response>'
#             '<GetDigits timeout="20" finishOnKey="#" numDigits="4" '
#             f'callbackUrl="{sx.escape(callback_url)}">'
#             '<Say>Welcome to YoSpaces. Enter your room PIN then press hash.</Say>'
#             '</GetDigits>'
#             '</Response>'
#         )
#         return _xml(xml)

#     # PIN entered via DTMF.
#     try:
#         space = Space.objects.get(pin=dtmf_digits)
#     except Space.DoesNotExist:
#         return _xml('<?xml version="1.0" encoding="UTF-8"?><Response><Say>Invalid PIN. Goodbye.</Say></Response>')

#     # If the room is not live yet, let the host in and activate it.
#     if _normalize_phone(caller_number) == _normalize_phone(space.host_phone):
#         if not space.is_active:
#             space.is_active = True
#             space.save(update_fields=["is_active"])
#     elif not space.is_active:
#         return _xml(
#             '<?xml version="1.0" encoding="UTF-8"?><Response>'
#             '<Say>This room is not live yet. Please try again later.</Say>'
#             '</Response>'
#         )

#     ActiveSpaceParticipant.objects.update_or_create(
#         space=space,
#         phone_number=_normalize_phone(caller_number or destination_number),
#         defaults={"call_session_id": session_id},
#     )
#     return _xml(_conference_xml(space, caller_number, f"Joining {space.name}"))


# def go_live(space_name, host_phone):
#     """
#     Starts a live space by activating it and calling all invited members.
#     The voice_callback() will place everyone into the conference room.
#     """
#     try:
#         space = Space.objects.get(
#             name=space_name,
#             host_phone=host_phone
#         )
#     except Space.DoesNotExist:
#         return "END Space not found."

#     # Activate the room
#     space.is_active = True
#     space.save(update_fields=["is_active"])

#     voice = africastalking.Voice

#     # Call the host first (host becomes moderator)
#     participants = [_normalize_phone(space.host_phone)]

#     # Call all invited members
#     participants.extend([
#         _normalize_phone(inv.phone_number)
#         for inv in space.invitees.all()
#     ])

#     # Remove duplicates
#     participants = list(set(participants))

#     try:
#         voice.call({
#             "callFrom": settings.AT_VOICE_NUMBER,
#             "callTo": participants,
#             "clientRequestId": str(space.pin)
#         })

#         logger.info(
#             "Started conference %s with %d participants",
#             space.name,
#             len(participants)
#         )

#         return (
#             f"END {space.name} is now LIVE!\n"
#             f"Calling {len(participants)} participant(s)..."
#         )

#     except Exception as e:
#         logger.exception("Conference start failed")

#         return (
#             "END Failed to start conference.\n"
#             f"{str(e)}"
#         )

# @csrf_exempt
# def conference_control(request):
#     """Proxy to Africa's Talking conference API for mute/unmute/kick/lock/unlock/etc."""
#     if request.method != "POST":
#         return JsonResponse({"status": False, "errorMessage": "POST only"}, status=405)

#     try:
#         payload = json.loads(request.body.decode("utf-8") or "{}")
#     except Exception:
#         payload = request.POST.dict()

#     if not AFRICASTALKING_LIVE_USERNAME or not AFRICASTALKING_LIVE_API_KEY:
#         return JsonResponse(
#             {"status": False, "errorMessage": "Missing Africa's Talking credentials"},
#             status=500,
#         )

#     payload.setdefault("username", 
#                        )

#     data = json.dumps(payload).encode("utf-8")
#     req = urllib.request.Request(AT_CONFERENCE_URL, data=data, method="POST")
#     req.add_header("Content-Type", "application/json")
#     req.add_header("Accept", "application/json")
#     basic = base64.b64encode(f"{AFRICASTALKING_LIVE_USERNAME}:{AFRICASTALKING_LIVE_API_KEY}".encode("utf-8")).decode("ascii")
#     req.add_header("Authorization", f"Basic {basic}")

#     try:
#         with urllib.request.urlopen(req, timeout=30) as resp:
#             body = resp.read().decode("utf-8")
#             return HttpResponse(body, content_type=resp.headers.get_content_type() or "application/json", status=resp.status)
#     except urllib.error.HTTPError as exc:
#         return JsonResponse(
#             {"status": False, "errorMessage": exc.read().decode("utf-8", errors="ignore")},
#             status=exc.code,
#         )
#     except Exception as exc:  # pragma: no cover - external network
#         logger.error("Conference API error: %s", exc)
#         return JsonResponse({"status": False, "errorMessage": str(exc)}, status=500)


# def active_listeners(request):
#     data = [
#         {
#             "space": p.space.name,
#             "phone": p.masked_phone(),
#             "joined_at": p.joined_at.isoformat(),
#         }
#         for p in ActiveSpaceParticipant.objects.select_related("space").filter(space__is_active=True)
#     ]
#     return JsonResponse({"active": data})

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

AT_VOICE_NUMBER = getattr(settings, "AT_VOICE_NUMBER", os.getenv("AT_VOICE_NUMBER", "+256323200925"))
AFRICASTALKING_LIVE_USERNAME = getattr(
    settings,
    "AFRICASTALKING_LIVE_USERNAME",
    os.getenv("AFRICASTALKING_LIVE_USERNAME", "yo_space"),
)
AFRICASTALKING_LIVE_API_KEY = getattr(
    settings,
    "AFRICASTALKING_LIVE_API_KEY",
    os.getenv("AFRICASTALKING_LIVE_API_KEY", ""),
)
AT_CONFERENCE_URL = getattr(
    settings,
    "AT_CONFERENCE_URL",
    os.getenv("AT_CONFERENCE_URL", "https://voice.africastalking.com/conference"),
)
AT_CALL_URL = getattr(
    settings,
    "AT_CALL_URL",
    os.getenv("AT_CALL_URL", "https://voice.africastalking.com/call"),
)


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


def _sanitize_space_name(name: str) -> str:
    name = (name or "").strip()
    name = re.sub(r"\s+", " ", name)
    name = re.sub(r"[^A-Za-z0-9_ -]", "", name)
    return name[:100] or "YoSpace"


def _latest_host_space(host_phone: str) -> Optional[Space]:
    return (
        Space.objects.filter(host_phone=_normalize_phone(host_phone))
        .order_by("-created_at", "-id")
        .first()
    )


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
    spaces = list(Space.objects.filter(is_active=True).order_by("-created_at", "-id")[:5])
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

    # Try SDK first if available.
    try:
        if africastalking:
            voice_client = getattr(africastalking, "Voice", None)
            call_fn = getattr(voice_client, "call", None)
            if callable(call_fn):
                # SDK style may vary by version; use the simplest form first.
                try:
                    call_fn(AT_VOICE_NUMBER, participants)
                    logger.info("SDK call placed for %s", space.name)
                    return
                except TypeError:
                    pass
    except Exception as exc:
        logger.warning("SDK voice call failed for %s: %s", space.name, exc)

    # REST fallback based on the current Voice API format.
    if not AFRICASTALKING_LIVE_API_KEY:
        logger.warning("Missing Africa's Talking API key; skipping outbound calls for %s", space.name)
        return

    payload = urllib.parse.urlencode(
        {
            "username": AFRICASTALKING_LIVE_USERNAME,
            "from": AT_VOICE_NUMBER,
            "to": json.dumps(participants),
        }
    ).encode("utf-8")

    req = urllib.request.Request(AT_CALL_URL, data=payload, method="POST")
    req.add_header("Accept", "application/json")
    req.add_header("Content-Type", "application/x-www-form-urlencoded")
    req.add_header("apiKey", AFRICASTALKING_LIVE_API_KEY)

    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            logger.info("Voice call API response for %s: %s", space.name, resp.read().decode("utf-8", errors="ignore"))
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
    """Activate the room and optionally call invitees. The conference still works without outbound calls."""
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

    # Main menu
    if text == "":
        return _plain(
            "CON Welcome to YoSpaces\n"
            "1. Host a Space\n"
            "2. Join a Space\n"
            "3. Browse Spaces\n"
            "4. About YoSpaces\n"
            "5. Exit"
        )

    # Host flow
    if text == "1":
        return _plain("CON Enter a name for your Space")

    if len(parts) == 2 and parts[0] == "1":
        space_name = _sanitize_space_name(parts[1])
        space, _created = Space.objects.get_or_create(
            name=space_name,
            host_phone=phone_number,
        )
        return _plain(_space_dashboard(space))

    # Manage members menu
    if len(parts) == 3 and parts[0] == "1" and parts[2] == "1":
        return _plain(_space_members_menu())

    # Add member
    if len(parts) == 4 and parts[0] == "1" and parts[2] == "1" and parts[3] == "1":
        return _plain("CON Enter member phone number")

    if len(parts) == 5 and parts[0] == "1" and parts[2] == "1" and parts[3] == "1":
        space = _current_space_for_host(phone_number, parts[1])
        if not space:
            return _plain("END Space not found. Please start over.")

        member_phone = _normalize_phone(parts[4])
        invitee, created = SpaceInvitee.objects.get_or_create(
            space=space,
            phone_number=member_phone,
        )
        if not created:
            return _plain("END That number is already invited.")

        _send_invite_sms(member_phone, space)
        return _plain(f"END {member_phone} invited to {space.name}.")

    # Remove member
    if len(parts) == 4 and parts[0] == "1" and parts[2] == "1" and parts[3] == "2":
        return _plain("CON Enter member phone number to remove")

    if len(parts) == 5 and parts[0] == "1" and parts[2] == "1" and parts[3] == "2":
        space = _current_space_for_host(phone_number, parts[1])
        if not space:
            return _plain("END Space not found. Please start over.")

        member_phone = _normalize_phone(parts[4])
        deleted, _ = SpaceInvitee.objects.filter(space=space, phone_number=member_phone).delete()
        return _plain("END Member removed." if deleted else "END Member not found in this space.")

    # View members
    if len(parts) == 4 and parts[0] == "1" and parts[2] == "1" and parts[3] == "3":
        space = _current_space_for_host(phone_number, parts[1])
        if not space:
            return _plain("END Space not found. Please start over.")
        return _plain(_members_text(space))

    if len(parts) == 4 and parts[0] == "1" and parts[2] == "1" and parts[3] == "4":
        space = _current_space_for_host(phone_number, parts[1])
        if not space:
            return _plain("END Space not found. Please start over.")
        return _plain(_space_dashboard(space))

    # Manage space menu
    if len(parts) == 3 and parts[0] == "1" and parts[2] == "2":
        space = _current_space_for_host(phone_number, parts[1])
        if not space:
            return _plain("END No active space found.")
        return _plain(_space_manage_menu(space))

    if len(parts) == 4 and parts[0] == "1" and parts[2] == "2" and parts[3] == "1":
        return _plain("CON Enter the new Space name")

    if len(parts) == 5 and parts[0] == "1" and parts[2] == "2" and parts[3] == "1":
        old_name = _sanitize_space_name(parts[1])
        new_name = _sanitize_space_name(parts[4])
        space = _current_space_for_host(phone_number, old_name)
        if not space:
            return _plain("END Space not found. Please start over.")
        if Space.objects.filter(name=new_name, host_phone=phone_number).exclude(pk=space.pk).exists():
            return _plain("END That space name already exists.")
        space.name = new_name
        space.save(update_fields=["name"])
        return _plain(_space_dashboard(space))

    if len(parts) == 4 and parts[0] == "1" and parts[2] == "2" and parts[3] == "2":
        space = _current_space_for_host(phone_number, parts[1])
        if not space:
            return _plain("END Space not found. Please start over.")
        return _plain(go_live(space.name, phone_number))

    if len(parts) == 4 and parts[0] == "1" and parts[2] == "2" and parts[3] == "3":
        space = _current_space_for_host(phone_number, parts[1])
        if not space:
            return _plain("END Space not found. Please start over.")
        return _plain(_space_dashboard(space))

    # Go live from dashboard
    if len(parts) == 3 and parts[0] == "1" and parts[2] == "3":
        space = _current_space_for_host(phone_number, parts[1])
        if not space:
            return _plain("END Space not found. Please start over.")
        return _plain(go_live(space.name, phone_number))

    # Join space flow
    if text == "2":
        return _plain("CON Enter Space PIN")

    if len(parts) == 2 and parts[0] == "2":
        pin = parts[1].strip()
        try:
            space = Space.objects.get(pin=pin)
        except Space.DoesNotExist:
            return _plain("END Invalid Space PIN.")

        # Host gets management menu, everyone else gets join instructions.
        if _normalize_phone(space.host_phone) == phone_number:
            return _plain(_space_dashboard(space))

        SpaceInvitee.objects.get_or_create(
            space=space,
            phone_number=phone_number,
        )
        return _plain(
            f"END You are registered for {space.name}.\n"
            f"Dial the voice line and enter PIN {space.pin} to join."
        )

    # Browse spaces: host sees management menu if they select their own space.
    # if text == "3":
    #     return _plain(_browse_menu())
    # =====================
    # Browse Spaces
    # =====================
    if text == "3":
        spaces = list(
            Space.objects.filter(is_active=True)
            .order_by("-created_at")[:5]
        )

        if not spaces:
            return _plain("END No active spaces right now.")

        response = "CON Active Spaces\n"

        for i, space in enumerate(spaces, start=1):
            response += f"{i}. {space.name}\n"

        return _plain(response)
    # User selected a space from Browse
if len(parts) == 2 and parts[0] == "3":

    spaces = list(
        Space.objects.filter(is_active=True)
        .order_by("-created_at")[:5]
    )

    try:
        index = int(parts[1]) - 1
        space = spaces[index]
    except (ValueError, IndexError):
        return _plain("END Invalid option.")

    # If caller is the host, show dashboard
    if _normalize_phone(phone_number) == _normalize_phone(space.host_phone):
        return _plain(_space_dashboard(space))

    # Otherwise allow joining
    SpaceInvitee.objects.get_or_create(
        space=space,
        phone_number=_normalize_phone(phone_number),
    )

    return _plain(
        f"END {space.name}\n"
        f"PIN: {space.pin}\n"
        "Dial the YoSpaces voice number and enter the PIN to join."
    )

    if len(parts) == 2 and parts[0] == "3":
        spaces = _active_spaces()
        try:
            choice = int(parts[1])
        except ValueError:
            return _plain("END Invalid option.")

        if choice < 1 or choice > len(spaces):
            return _plain("END Invalid option.")

        space = spaces[choice - 1]
        if _normalize_phone(space.host_phone) == phone_number:
            return _plain(_space_dashboard(space))

        # Non-hosts can join by PIN; this keeps the flow simple and reliable.
        SpaceInvitee.objects.get_or_create(
            space=space,
            phone_number=phone_number,
        )
        return _plain(
            f"END {space.name} selected.\n"
            f"Dial the voice line and enter PIN {space.pin} to join."
        )

    if text == "4":
        return _plain(
            "END YoSpaces is a 2G-first social audio platform built for local communities."
        )

    if text == "5":
        return _plain("END Thanks for using YoSpaces.")

    return _plain("END Invalid option. Please try again.")


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

    # Call ended: clean up any active participant record.
    if is_active == "0":
        ActiveSpaceParticipant.objects.filter(call_session_id=session_id).delete()
        return _xml('<?xml version="1.0" encoding="UTF-8"?><Response></Response>')

    # If clientRequestId exists, use it as the room PIN.
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

    # First inbound response: ask for the PIN.
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

    # PIN entered via DTMF.
    try:
        space = Space.objects.get(pin=dtmf_digits)
    except Space.DoesNotExist:
        return _xml('<?xml version="1.0" encoding="UTF-8"?><Response><Say>Invalid PIN. Goodbye.</Say></Response>')

    caller_number = _normalize_phone(caller_number or destination_number)

    # Host can activate the room by calling in.
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
    """Proxy to Africa's Talking conference API for mute/unmute/kick/lock/unlock/etc."""
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

    # Required fields are passed through from the client, but we set sensible defaults.
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

