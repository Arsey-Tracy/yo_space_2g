To integrate Pesapal in Django, you have two main options: use the community-maintained `django-pesapal` package (fastest) or implement a custom integration against Pesapal’s API v3 (more control). Below is a concise, end‑to‑end guide for both approaches, with emphasis on API v3 since that’s what Pesapal recommends. [dev](https://dev.to/joy_nyayieka/integrating-pesapal-api-30-on-django-58i0)

## Option A — Quick start with `django-pesapal` (recommended for MVPs)

This package wraps Pesapal’s API and gives you ready-made views, models, and URL patterns. [github](https://github.com/odero/django-pesapal)

### 1. Install and configure

```bash
pip install django-pesapal
```

In `settings.py`:

```python
INSTALLED_APPS = [
    # ...
    "django.contrib.sites",
    "django_pesapal",
    "django_pesapalv3",  # use this for API v3
]

# Pesapal credentials (from your Pesapal merchant dashboard)
PESAPAL_DEMO = True  # sandbox; set False in production
PESAPAL_CONSUMER_KEY = "your_consumer_key"
PESAPAL_CONSUMER_SECRET = "your_consumer_secret"

# Where to redirect after payment
PESAPAL_TRANSACTION_DEFAULT_REDIRECT_URL = "orders:order_detail"  # reversible URL name
```

Include URLs in your project’s `urls.py`:

```python
from django.urls import path, include

urlpatterns = [
    # ...
    path("payments/v3/", include("django_pesapalv3.urls")),
    # path("payments/", include("django_pesapal.urls")),  # classic API if needed
]
```

Run migrations:

```bash
python manage.py migrate
```

### 2. Create a payment view

Use the provided mixin to generate the Pesapal checkout URL (or iframe). [github](https://github.com/odero/django-pesapal)

```python
import uuid
from django.urls import reverse
from django.views.generic import TemplateView
from django_pesapalv3.views import PaymentRequestMixin

class PaymentView(PaymentRequestMixin, TemplateView):
    template_name = "payments/payment.html"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["pesapal_url"] = self.get_pesapal_payment_iframe()
        return ctx

    def get_pesapal_payment_iframe(self):
        ipn = self.get_default_ipn()  # or register your own IPN

        order_info = {
            "id": str(uuid.uuid4()),
            "currency": "UGX",  # or KES, TZS, etc.
            "amount": 50000,
            "description": "Order #1234",
            "callback_url": self.build_url(reverse("django_pesapalv3:transaction_completed")),
            "notification_id": ipn,
            "billing_address": {
                "first_name": "John",
                "last_name": "Doe",
                "email": "john@example.com",
                "phone_number": "+256700000000",
                "country_code": "UG",
            },
        }
        resp = self.submit_order_request(**order_info)
        return resp["redirect_url"]
```

Template (`payment.html`) can simply redirect or embed the `pesapal_url` in an iframe. After payment, Pesapal redirects to the configured callback and then to your `PESAPAL_TRANSACTION_DEFAULT_REDIRECT_URL`. [github](https://github.com/odero/django-pesapal)

## Option B — Custom integration with Pesapal API v3 (full control)

This is ideal if you want to own the flow, add custom logic, or avoid extra dependencies. The core steps are: authenticate → register IPN → submit order → handle callback/IPN → confirm status. [dev](https://dev.to/joy_nyayieka/integrating-pesapal-api-30-on-django-58i0)

### 1. Set up credentials and environment

In `.env`:

```env
PESAPAL_CONSUMER_KEY=your_consumer_key
PESAPAL_CONSUMER_SECRET=your_consumer_secret
PESAPAL_BASE_URL=https://cybqa.pesapal.com/pesapalv3/api/  # sandbox
# PESAPAL_BASE_URL=https://pay.pesapal.com/pesapalv3/api/   # production
PESAPAL_IPN_ID=  # filled after registering IPN
```

In `settings.py`:

```python
from decouple import config

PESAPAL_CONSUMER_KEY = config("PESAPAL_CONSUMER_KEY")
PESAPAL_CONSUMER_SECRET = config("PESAPAL_CONSUMER_SECRET")
PESAPAL_BASE_URL = config("PESAPAL_BASE_URL")
PESAPAL_IPN_ID = config("PESAPAL_IPN_ID", default="")
```

Install dependencies:

```bash
pip install requests python-decouple djangorestframework
```

### 2. Create a service layer (`pesapal_service.py`)

This module handles OAuth tokens, IPN registration, order submission, and status checks. [dev](https://dev.to/joy_nyayieka/integrating-pesapal-api-30-on-django-58i0)

```python
import requests
from django.conf import settings

BASE_URL = settings.PESAPAL_BASE_URL

def generate_access_token():
    url = f"{BASE_URL}api/Auth/RequestToken"
    payload = {
        "consumer_key": settings.PESAPAL_CONSUMER_KEY,
        "consumer_secret": settings.PESAPAL_CONSUMER_SECRET,
    }
    headers = {"Accept": "application/json", "Content-Type": "application/json"}
    resp = requests.post(url, json=payload, headers=headers, timeout=10)
    resp.raise_for_status()
    return resp.json()["token"]

def register_ipn_url(access_token, ipn_url):
    url = f"{BASE_URL}api/URLSetup/RegisterIPN"
    payload = {"url": ipn_url, "ipn_notification_type": "GET"}
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Accept": "application/json",
        "Content-Type": "application/json",
    }
    resp = requests.post(url, json=payload, headers=headers, timeout=10)
    resp.raise_for_status()
    return resp.json()

def submit_order_request(access_token, payload):
    url = f"{BASE_URL}api/Transactions/SubmitOrderRequest"
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Accept": "application/json",
        "Content-Type": "application/json",
    }
    resp = requests.post(url, json=payload, headers=headers, timeout=10)
    resp.raise_for_status()
    return resp.json()

def get_transaction_status(access_token, tracking_id, merchant_reference):
    url = f"{BASE_URL}api/Transactions/GetTransactionStatus"
    headers = {"Authorization": f"Bearer {access_token}", "Accept": "application/json"}
    params = {"order_tracking_id": tracking_id, "order_merchant_reference": merchant_reference}
    resp = requests.get(url, headers=headers, params=params, timeout=10)
    resp.raise_for_status()
    return resp.json()
```

### 3. Define a Payment model

Store orders and track status locally. [dev](https://dev.to/joy_nyayieka/integrating-pesapal-api-30-on-django-58i0)

```python
from django.db import models

class Payment(models.Model):
    order_id = models.CharField(max_length=100, unique=True)
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    currency = models.CharField(max_length=3, default="UGX")
    status = models.CharField(max_length=50, default="PENDING")  # PENDING, COMPLETED, FAILED
    tracking_id = models.CharField(max_length=100, null=True, blank=True)
    merchant_reference = models.CharField(max_length=100, unique=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
```

### 4. Implement views (initiate payment, callback, IPN)

```python
import json, uuid
from django.http import JsonResponse, HttpResponse
from django.shortcuts import redirect, render
from django.views.decorators.csrf import csrf_exempt
from django.conf import settings
from . import pesapal_service
from .models import Payment

def create_order_view(request):
    # Accept JSON or form data
    if request.content_type == "application/json":
        data = json.loads(request.body)
        amount = float(data.get("amount", 0))
        email = data.get("email", "customer@example.com")
        phone = data.get("phone", "+256700000000")
        first_name = data.get("first_name", "Customer")
        last_name = data.get("last_name", "Name")
    else:
        amount = float(request.POST.get("amount", 0))
        email = request.POST.get("email", "customer@example.com")
        phone = request.POST.get("phone", "+256700000000")
        first_name = request.POST.get("first_name", "Customer")
        last_name = request.POST.get("last_name", "Name")

    token = pesapal_service.generate_access_token()

    merchant_reference = str(uuid.uuid4())
    payload = {
        "id": merchant_reference,
        "currency": "UGX",
        "amount": amount,
        "description": f"Payment for order {merchant_reference[:8]}",
        "callback_url": "https://yourdomain.com/payments/pesapal/callback/",
        "notification_id": settings.PESAPAL_IPN_ID,  # register this first
        "billing_address": {
            "email_address": email,
            "phone_number": phone,
            "country_code": "UG",
            "first_name": first_name,
            "last_name": last_name,
            "line_1": "Kampala",
            "city": "Kampala",
        },
    }

    resp = pesapal_service.submit_order_request(token, payload)
    redirect_url = resp.get("redirect_url")

    # Save local record
    Payment.objects.create(
        order_id=merchant_reference,
        amount=amount,
        currency="UGX",
        merchant_reference=merchant_reference,
        tracking_id=resp.get("order_tracking_id"),
        status="PENDING",
    )

    return JsonResponse({"redirect_url": redirect_url}) if redirect_url else JsonResponse({"error": "Failed"}, status=400)

@csrf_exempt
def ipn_listener(request):
    # Pesapal sends GET with tracking_id & merchant_reference
    tracking_id = request.GET.get("order_tracking_id")
    merchant_reference = request.GET.get("order_merchant_reference")

    # Confirm status server-side before trusting IPN
    token = pesapal_service.generate_access_token()
    status_data = pesapal_service.get_transaction_status(token, tracking_id, merchant_reference)
    payment_status = status_data.get("payment_status")  # COMPLETED, FAILED, etc.

    try:
        payment = Payment.objects.get(merchant_reference=merchant_reference)
        payment.status = payment_status
        payment.tracking_id = tracking_id
        payment.save()
    except Payment.DoesNotExist:
        pass

    return HttpResponse("IPN received", status=200)

def payment_callback(request):
    tracking_id = request.GET.get("order_tracking_id")
    merchant_reference = request.GET.get("order_merchant_reference")

    token = pesapal_service.generate_access_token()
    status_data = pesapal_service.get_transaction_status(token, tracking_id, merchant_reference)
    payment_status = status_data.get("payment_status")

    if payment_status == "COMPLETED":
        return redirect("orders:order_detail", ref=merchant_reference)
    else:
        return render(request, "payments/payment_failed.html", {"ref": merchant_reference})
```

Wire these in `urls.py`:

```python
from django.urls import path
from . import views

urlpatterns = [
    path("payments/pesapal/create/", views.create_order_view, name="pesapal_create"),
    path("payments/pesapal/ipn/", views.ipn_listener, name="pesapal_ipn"),
    path("payments/pesapal/callback/", views.payment_callback, name="pesapal_callback"),
]
```

### 5. Register your IPN URL

During development, use ngrok to expose a public URL, then call your IPN registration endpoint (or Pesapal’s `RegisterIPN`) to get an `notification_id`. Save that ID in `PESAPAL_IPN_ID`. [dev](https://dev.to/joy_nyayieka/integrating-pesapal-api-30-on-django-58i0)

Example registration helper view (one-time):

```python
def register_ipn_view(request):
    ipn_url = request.GET["url"]  # e.g. https://your-ngrok-url/payments/pesapal/ipn/
    token = pesapal_service.generate_access_token()
    resp = pesapal_service.register_ipn_url(token, ipn_url)
    return JsonResponse(resp)
```

After registration, Pesapal returns an IPN ID; store it in `.env`. [dev](https://dev.to/joy_nyayieka/integrating-pesapal-api-30-on-django-58i0)

## Production checklist

- Switch `PESAPAL_BASE_URL` to `https://pay.pesapal.com/pesapalv3/api/`. [dev](https://dev.to/joy_nyayieka/integrating-pesapal-api-30-on-django-58i0)
- Ensure all public endpoints use HTTPS and are in `ALLOWED_HOSTS`. [dev](https://dev.to/joy_nyayieka/integrating-pesapal-api-30-on-django-58i0)
- Cache the OAuth token (it’s time-limited) instead of fetching on every request. [dev](https://dev.to/joy_nyayieka/integrating-pesapal-api-30-on-django-58i0)
- Add robust error handling and logging around all HTTP calls. [dev](https://dev.to/joy_nyayieka/integrating-pesapal-api-30-on-django-58i0)
- Test with small real transactions before going live. [linkedin](https://www.linkedin.com/pulse/beginners-comprehensive-guide-integrating-pesapal-payment-arishaba-2s7af)

If you tell me your Django version and whether you prefer DRF or classic views, I can tailor a minimal, copy‑pasteable integration snippet for your exact stack (including a sample `Payment` model and URL config).