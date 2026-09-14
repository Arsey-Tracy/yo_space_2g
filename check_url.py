import django
import os

os.environ["DJANGO_SETTINGS_MODULE"] = "yo_space_project.settings"
django.setup()

from django.urls import resolve, reverse

# Try to resolve /api/sms/broadcasts/
try:
    match = resolve("/api/sms/broadcasts/")
    print(f"Resolved to: {match}")
except Exception as e:
    print(f"Error resolving: {e}")

# Try to reverse the URL
try:
    url = reverse("sms:broadcast-list")
    print(f"Reverse sms:broadcast-list: {url}")
except Exception as e:
    print(f"Reverse sms:broadcast-list error: {e}")

# Try other reverse names
try:
    url = reverse("broadcast-list")
    print(f"Reverse broadcast-list: {url}")
except Exception as e:
    print(f"Reverse broadcast-list error: {e}")
