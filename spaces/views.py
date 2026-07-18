from django.http import HttpResponse
from django.views.decorators.csrf import csrf_exempt

# Configure Africastalking credentials

# Configure Gemini Credentials

# Implement a basic USSD call back for africasalking
@csrf_exempt
def ussd_callback(request):
    session_id = request.POST.get("sessionId", "")
    service_code = request.POST.get("serviceCode", "")
    phone_number = request.POST.get("phoneNumber", "")
    text = request.POST.get("text", "")
    
    response = ""
    if text == "":
        response = "CON YoSpaces\n"
        response += "1. Join a Space\n"
        response += "2. Host a Space\n"
        response += "3. Browse a Space\n"
        response += "4. About YoSpace\n"
        response += "5. Exit\n"
    elif text == "1":
        response = "END Joining a space is still under development. We are sorry for any interruptions."
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


