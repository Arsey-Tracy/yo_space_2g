from django.http import HttpResponse, JsonResponse
from django.views.decorators.csrf import csrf_exempt
import xml.sax.saxutils as sx
import logging
from .models import *
import africastalking

logger = logging.getLogger("yospaces")

# Configure AfricasTalking credentials

# Configure Gemini Credentials

# Implement a basic USSD call back for africasalking
@csrf_exempt
def ussd_callback(request):
    session_id = request.POST.get("sessionId", "")
    service_code = request.POST.get("serviceCode", "")
    phone_number = request.POST.get("phoneNumber", "")
    text = request.POST.get("text", "")
    
    input_parts = text.split("*") if text else []
    
    response = ""
    
    if text == "":
        response = "CON YoSpaces\n"
        response += "1. Host a Space\n"
        response += "2. Join a Space\n"
        response += "3. Browse a Space\n"
        response += "4. About YoSpace\n"
        response += "5. Exit\n"
    elif text == "1":
        response = "CON Enter a short name for your Space:(e.g FamilyTalks)"
    elif len(input_parts) == 2 and input_parts[0] == "1":
        space_name = input_parts[1]
        Space.objects.get_or_create(name=space_name, host_phone=phone_number)
        
        # send and sms or continue to add memebers phonenumbers and save them to the database
        response = f"CON {space_name} Dashboard\n"
        response += "1. Manage Members\n"
        response += "2. Manage Space\n"
        response += "3. Go Live\n"
    elif len(input_parts) == 3 and input_parts[0] == "1" and input_parts[2] == "1":
    # elif text == "1*1":
        response = "CON Manage Members\n"
        response += "1. Add Member\n"
        response += "2. Remove Member\n"
        response += "3. View Members\n"
        
    elif text == "1*2":
        space_name = Space.name
        response == f"CON {space_name}\n"
        response += "1. Edit Space\n"
        response += "2. Go Live\n"
    elif text == "2":
        response = "END Hosting a space is still under development. We are sorry for any interruptions."
    elif text == "3":
        response = "END Browsing a space is still under development. We are sorry for any interruptions."
    elif text == "4":
        response = "END YoSpace is a 2G first social space for locals."
    elif text == "5":
        response = "END Thanks for using YoSpaces, see you soon."
    else:
        response = "END Invalid Option. Please Try Again."
    return HttpResponse(response, content_type="text/plain")

        

# implement voice support for the application
def voice_callback():
    pass


