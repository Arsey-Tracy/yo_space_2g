from django.http import HttpResponse, JsonResponse
from django.views.decorators.csrf import csrf_exempt
import xml.sax.saxutils as sx
import logging
from .models import *
import africastalking

logger = logging.getLogger("yospaces")

# Configure AfricasTalking credentials

# Configure Gemini Credentials

@csrf_exempt
def ussd_callback(request):
    session_id = request.POST.get("sessionId", "")
    service_code = request.POST.get("serviceCode", "")
    phone_number = request.POST.get("phoneNumber", "")
    text = request.POST.get("text", "")

    input_parts = text.split("*") if text else []

    # ==========================
    # MAIN MENU
    # ==========================
    if text == "":
        response = "CON Welcome to YoSpaces\n"
        response += "1. Host a Space\n"
        response += "2. Join a Space\n"
        response += "3. Browse Spaces\n"
        response += "4. About YoSpaces\n"
        response += "5. Exit"
        

    # ==========================
    # HOST SPACE
    # ==========================
    elif text == "1":
        response = "CON Enter a name for your Space"

    elif len(input_parts) == 2 and input_parts[0] == "1":
        space_name = input_parts[1]

        space, created = Space.objects.get_or_create(
            name=space_name,
            host_phone=phone_number
        )

        response = f"CON {space.name} Dashboard\n"
        response += "1. Manage Members\n"
        response += "2. Manage Space\n"
        response += "3. Go Live"
        

    # ==========================
    # MANAGE MEMBERS
    # ==========================
    elif len(input_parts) == 3 and input_parts[0] == "1" and input_parts[2] == "1":

        response = "CON Manage Members\n"
        response += "1. Add Member\n"
        response += "2. Remove Member\n"
        response += "3. View Members"

    # ==========================
    # MANAGE SPACE
    # ==========================
    elif len(input_parts) == 3 and input_parts[0] == "1" and input_parts[2] == "2":

        try:
            space = Space.objects.filter(
                host_phone=phone_number
            ).latest("id")

            response =  f"CON {space.name}\n"
            response += "1. Edit Space\n"
            response += "2. Go Live"
            

        except Space.DoesNotExist:
            response = "END No active space found."

    # ==========================
    # GO LIVE
    # ==========================
    elif len(input_parts) == 3 and input_parts[0] == "1" and input_parts[2] == "3":

        response =  "END Space is Live!\n Participants will receive calls shortly."
      

    # ==========================
    # JOIN SPACE
    # ==========================
    elif text == "2":
        response = "CON Enter Space PIN"

    elif len(input_parts) == 2 and input_parts[0] == "2":

        pin = input_parts[1]

        try:
            space = Space.objects.get(pin=pin)

            response =  f"END Joined {space.name} successfully!"

        except Space.DoesNotExist:
            response = "END Invalid Space PIN."

    # ==========================
    # BROWSE
    # ==========================
    elif text == "3":
        response = "END Browse Spaces coming soon."

    # ==========================
    # ABOUT
    # ==========================
    elif text == "4":
        response =  "END YoSpaces is a 2G-first social audio platform built for local communities."

    # ==========================
    # EXIT
    # ==========================
    elif text == "5":
        response = "END Thanks for using YoSpaces."

    # ==========================
    # INVALID
    # ==========================
    else:
        response = "END Invalid option."

    return HttpResponse(response, content_type="text/plain")        

# implement voice support for the application
def voice_callback():
    pass


