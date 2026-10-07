from __future__ import annotations

from django.http import HttpResponse
from django.views.decorators.csrf import csrf_exempt

from account.models import Organization
from spaces.models import Space, SpaceMember
from survey.models import Survey

from .models import UssdSession
from .services import initiate_ussd_broadcast
from .utils import _normalize_phone


# ==========================================
# Phone / session helpers
# ==========================================


def _plain(text: str) -> HttpResponse:
    return HttpResponse(text, content_type="text/plain")


def _current_input(text: str) -> str:
    """Extract the last ``*``-delimited segment from USSD input text."""
    parts = (text or "").split("*")
    return parts[-1].strip() if parts else ""


def _get_session(phone_number: str) -> UssdSession | None:
    """Return an active USSD session for *phone_number*, or ``None`` when
    no un-expired session exists (caller should re-enter the main menu).
    """
    session = UssdSession.objects.active().filter(phone_number=phone_number).first()
    if session is None:
        return None
    session.extend()
    return session


def _get_or_create_session(phone_number: str) -> UssdSession:
    """Get an active session or create a fresh one in ``main_menu`` state."""
    session = _get_session(phone_number)
    if session is None:
        session = UssdSession.objects.create(
            phone_number=phone_number,
            state="main_menu",
            data={},
        )
    return session


def _clear_session(phone_number: str) -> None:
    """Delete the USSD session for *phone_number* (if any)."""
    UssdSession.objects.filter(phone_number=phone_number).delete()


# ==========================================
# Host detection
# ==========================================


def _is_host(phone_number: str) -> bool:
    """Determine whether *phone_number* belongs to an authorised host.

    A phone number is authorised when it is either:
    • The owner of any ``Organization``, **or**
    • The ``host_phone`` of a ``Space`` whose owning organization is itself
      owned by that same phone number.

    Simply having a ``CustomUser`` account is **not** sufficient — see
    ``update.md`` §2.
    """
    return Organization.objects.filter(owner__phone=phone_number).exists() or (
        Space.objects.filter(
            host_phone=phone_number,
            organization__owner__phone=phone_number,
        ).exists()
    )


# ==========================================
# Host spaces helper
# ==========================================


def _host_spaces(phone_number: str):
    return (
        Space.objects.filter(host_phone=phone_number)
        .select_related("organization")
        .order_by("-created_at")
    )


# ==========================================
# USSD callback (Africa's Talking)
# ==========================================


@csrf_exempt
def ussd_callback(request):
    """
    Africa's Talking USSD Callback Handler.

    Conversation state is persisted in the ``UssdSession`` database model so
    that sessions survive restarts and work across multiple workers.

    Only IDs and state identifiers are stored in ``session.data`` — never
    PINs, passwords, or other secrets.
    """
    if request.method != "POST":
        return _plain("END Invalid request method.")

    phone_number = _normalize_phone(request.POST.get("phoneNumber", ""))
    text = (request.POST.get("text", "") or "").strip()
    current = _current_input(text)

    if not phone_number:
        return _plain("END Phone number is required.")

    # USSD cleanup of expired sessions (lightweight, runs on each request)
    UssdSession.objects.cleanup_expired()

    session = _get_or_create_session(phone_number)

    # text == "" → fresh session (user just dialed)
    if text == "":
        session.reset()
        return _main_menu(phone_number)

    return _dispatch(phone_number, session, text, current)


# ==========================================
# Main menu
# ==========================================


def _main_menu(phone_number: str) -> HttpResponse:
    if _is_host(phone_number):
        return _plain(
            "CON Welcome Host to YoSpaces\n"
            "1. Host a Space\n"
            "2. Manage My Spaces\n"
            "3. Broadcast SMS\n"
            "4. Browse Public Spaces\n"
            "5. Exit"
        )
    return _plain(
        "CON Welcome to YoSpaces\n"
        "1. Join Space via PIN\n"
        "2. Browse Public Spaces\n"
        "3. Take Active Surveys\n"
        "4. About YoSpaces\n"
        "5. Exit"
    )


# ==========================================
# Dispatch
# ==========================================


def _dispatch(
    phone_number: str, session: UssdSession, text: str, current: str
) -> HttpResponse:
    is_host = _is_host(phone_number)

    if is_host:
        return _host_dispatcher(phone_number, session, text, current)
    return _member_dispatcher(phone_number, session, text, current)


# ==========================================
# Host workflow
# ==========================================


def _host_dispatcher(
    phone_number: str, session: UssdSession, text: str, current: str
) -> HttpResponse:
    parts = (text or "").split("*")

    # --- Option 1: Host a Space ---
    if text == "1":
        session.state = "host_space_name"
        session.data = {}
        session.save(update_fields=["state", "data"])
        return _plain("CON Enter a name for your Space:")

    if session.state == "host_space_name":
        space_name = current[:100]
        if not space_name:
            return _plain("CON Enter a name for your Space:")
        org = Organization.objects.filter(owner__phone=phone_number).first()
        if not org:
            _clear_session(phone_number)
            return _plain("END No organization found for this host.")

        space = Space.objects.create(
            name=space_name,
            host_phone=phone_number,
            organization=org,
        )
        _clear_session(phone_number)
        return _plain(
            f"END Space '{space.name}' created!\n"
            f"PIN: {space.pin}\n"
            f"Members can dial in to join."
        )

    # --- Option 2: Manage My Spaces ---
    if text == "2":
        spaces = list(_host_spaces(phone_number)[:5])
        if not spaces:
            return _plain("END You have no active spaces.")
        lines = ["CON My Spaces:"]
        for idx, sp in enumerate(spaces, start=1):
            lines.append(f"{idx}. {sp.name} (PIN: {sp.pin})")
        return _plain("\n".join(lines))

    # --- Option 3: Broadcast SMS ---
    # Flow:  text="3"        → list spaces for selection
    #        text="3*<n>"    → enter message
    #        text="3*<n>*<msg>" → send via wallet service
    if text == "3":
        spaces = list(_host_spaces(phone_number)[:5])
        if not spaces:
            _clear_session(phone_number)
            return _plain("END You have no spaces to broadcast to.")
        lines = ["CON Select Space to Broadcast:"]
        for idx, sp in enumerate(spaces, start=1):
            lines.append(f"{idx}. {sp.name}")
        session.state = "host_broadcast_select"
        session.data = {}
        session.save(update_fields=["state", "data"])
        return _plain("\n".join(lines))

    if session.state == "host_broadcast_select" and len(parts) == 2:
        try:
            space_idx = int(parts[1]) - 1
        except (ValueError, IndexError):
            return _plain("END Invalid selection.")
        spaces = list(_host_spaces(phone_number)[:5])
        if 0 <= space_idx < len(spaces):
            selected_space = spaces[space_idx]
            session.state = "host_broadcast_msg"
            session.data = {"selected_space_id": selected_space.id}
            session.space = selected_space
            session.save(update_fields=["state", "data", "space"])
            return _plain(
                f"CON Enter broadcast SMS message for '{selected_space.name}':"
            )
        return _plain("END Invalid space selection.")

    if session.state == "host_broadcast_msg" and len(parts) >= 3:
        space_id = session.data.get("selected_space_id")
        if not space_id:
            _clear_session(phone_number)
            return _plain("END Session expired. Please start over.")

        try:
            space = Space.objects.select_related("organization").get(
                id=space_id, host_phone=phone_number
            )
        except Space.DoesNotExist:
            _clear_session(phone_number)
            return _plain("END Space not found or not owned by you.")

        # Verify ownership again right before sending (defence in depth)
        if not _is_host(phone_number):
            _clear_session(phone_number)
            return _plain("END Authorization failed.")

        message = current
        if not message:
            return _plain(f"CON Enter broadcast SMS message for '{space.name}':")

        recipients = list(space.members.values_list("phone_number", flat=True))

        broadcast_record, error = initiate_ussd_broadcast(
            space=space,
            phone_numbers=recipients,
            message=message,
            initiated_by=None,
        )

        _clear_session(phone_number)

        if error:
            return _plain(f"END {error}")

        return _plain(
            f"END Broadcast sent to {len(recipients)} members of {space.name}."
        )

    # --- Option 4: Browse Public Spaces (shared with members) ---
    if text == "4" or (
        session.state == "browse_public" and len(parts) == 1 and parts[0] == "4"
    ):
        return _browse_public_spaces(phone_number, session)

    # --- Option 5: Exit ---
    if text == "5":
        _clear_session(phone_number)
        return _plain("END Thank you for using Yo-Spaces.")

    return _plain("END Invalid selection. Goodbye.")


# ==========================================
# Member / End-user workflow
# ==========================================


def _member_dispatcher(
    phone_number: str, session: UssdSession, text: str, current: str
) -> HttpResponse:
    parts = (text or "").split("*")

    # --- Option 1: Join Space via PIN ---
    if text == "1":
        session.state = "join_space_pin"
        session.data = {}
        session.save(update_fields=["state", "data"])
        return _plain("CON Enter 4-digit Space PIN:")

    if session.state == "join_space_pin":
        pin = current.strip()
        if not pin:
            return _plain("CON Enter 4-digit Space PIN:")

        space = Space.objects.filter(pin=pin).first()
        if not space:
            _clear_session(phone_number)
            return _plain("END Invalid PIN. Space not found.")

        SpaceMember.objects.get_or_create(
            space=space,
            phone_number=phone_number,
            defaults={"name": "", "role": SpaceMember.Role.MEMBER},
        )
        _clear_session(phone_number)
        return _plain(
            f"END Registered for '{space.name}'!\n"
            f"Dial the YoSpaces Voice line and enter PIN {space.pin} to join voice calls."
        )

    # --- Option 2: Browse Public Spaces ---
    if text == "2":
        return _browse_public_spaces(phone_number, session)

    # --- Option 3: Take Active Surveys ---
    if text == "3":
        return _list_active_surveys(phone_number, session)

    # --- Option 4: About ---
    if text == "4":
        _clear_session(phone_number)
        return _plain(
            "END Yo-Spaces is a 2G community communication platform powered by SMS & Voice."
        )

    # --- Option 5: Exit ---
    if text == "5":
        _clear_session(phone_number)
        return _plain("END Thank you for using Yo-Spaces.")

    return _plain("END Invalid selection. Goodbye.")


# ==========================================
# Shared sub-flows
# ==========================================


def _browse_public_spaces(phone_number: str, session: UssdSession) -> HttpResponse:
    spaces = list(Space.objects.filter(is_public=True).order_by("-created_at")[:5])
    if not spaces:
        _clear_session(phone_number)
        return _plain("END No public spaces available.")

    lines = ["CON Public Spaces:"]
    for idx, sp in enumerate(spaces, start=1):
        lines.append(f"{idx}. {sp.name} (PIN: {sp.pin})")
    return _plain("\n".join(lines))


def _list_active_surveys(phone_number: str, session: UssdSession) -> HttpResponse:
    surveys = list(
        Survey.objects.filter(is_active=True)
        .select_related("space")
        .order_by("-created_at")[:5]
    )
    if not surveys:
        _clear_session(phone_number)
        return _plain("END No active surveys available.")

    lines = ["CON Active Surveys:"]
    for idx, s in enumerate(surveys, start=1):
        lines.append(f"{idx}. {s.title}")
    session.state = "take_survey"
    session.data = {"survey_id": surveys[0].id}
    session.save(update_fields=["state", "data"])
    return _plain("\n".join(lines))
