# import base64
# import logging
# import time
# import requests

# from decimal import Decimal
# from typing import Any, Dict, Optional
# from django.conf import settings

# logger = logging.getLogger(__name__)


# class PesapalError(Exception):
#     """Raised when Pesapal returns an error."""


# def normalize_pesapal_base_url(raw_url: str) -> str:
#     """Return the Pesapal host root (no trailing /api).

#     Clients append `/api/Auth/RequestToken`, so values like
#     `https://cybqa.pesapal.com/pesapalv3/api` or the invalid
#     `https://api.pesapal.com/api/v3` must be normalized.
#     """
#     url = (raw_url or "").strip().rstrip("/")
#     aliases = {
#         "https://api.pesapal.com/api/v3": "https://pay.pesapal.com/v3",
#         "https://api.pesapal.com": "https://pay.pesapal.com/v3",
#         "https://pay.pesapal.com/v3/api": "https://pay.pesapal.com/v3",
#         "https://cybqa.pesapal.com/pesapalv3/api": "https://cybqa.pesapal.com/pesapalv3",
#     }
#     url = aliases.get(url, url)
#     if url.endswith("/api"):
#         url = url[:-4]
#     return url.rstrip("/")


# def map_pesapal_transaction_status(payload: dict) -> str:
#     """Pesapal `status` is an HTTP-like code (e.g. 200), not payment state."""
#     if not payload:
#         return "pending"

#     description = str(payload.get("payment_status_description") or "").strip().lower()
#     raw_code = payload.get("status_code", payload.get("payment_status_code"))
#     try:
#         status_code = int(raw_code)
#     except (TypeError, ValueError):
#         status_code = None

#     if description == "completed" or status_code == 1:
#         return "completed"
#     if description in {"failed", "invalid", "error"} or status_code == 2:
#         return "failed"
#     if description in {"reversed", "cancelled", "canceled"} or status_code == 3:
#         return "cancelled"
#     return "pending"


# class PesapalClient:
#     """
#     Small wrapper around Pesapal API 3.0.
#     """

#     def __init__(self):
#         self.base_url = normalize_pesapal_base_url(
#             getattr(settings, "PESAPAL_BASE_URL", "") or "https://cybqa.pesapal.com/pesapalv3"
#         )

#         self.consumer_key = (settings.PESAPAL_CONSUMER_KEY or "").strip().strip('"')
#         self.consumer_secret = (settings.PESAPAL_CONSUMER_SECRET or "").strip().strip('"')

#         if not self.consumer_key:
#             raise PesapalError(
#                 "PESAPAL_CONSUMER_KEY is not configured."
#             )

#         if not self.consumer_secret:
#             raise PesapalError(
#                 "PESAPAL_CONSUMER_SECRET is not configured."
#             )

#     # ---------------------------------------------------------
#     # Helpers
#     # ---------------------------------------------------------

#     @staticmethod
#     def _headers(token=None):
#         headers = {
#             "Accept": "application/json",
#             "Content-Type": "application/json",
#         }

#         if token:
#             headers["Authorization"] = f"Bearer {token}"

#         return headers

#     @staticmethod
#     def _handle_response(response):
#         try:
#             data = response.json()
#         except ValueError:
#             data = {
#                 "message": response.text,
#             }

#         if isinstance(data, list):
#             if not response.ok:
#                 raise PesapalError("Pesapal API error")
#             return data

#         api_status = str(data.get("status", "")).strip()
#         if api_status and api_status not in {"200", "0"} and not data.get("token") and not data.get("order_tracking_id"):
#             error = data.get("error") if isinstance(data.get("error"), dict) else {}
#             message = error.get("message") or data.get("message") or "Pesapal API error"
#             logger.error("Pesapal API status %s - %s", api_status, data)
#             raise PesapalError(message)

#         if not response.ok:
#             error = data.get("error")

#             if isinstance(error, dict):
#                 message = error.get(
#                     "message",
#                     "Pesapal API error",
#                 )
#             else:
#                 message = data.get(
#                     "message",
#                     "Pesapal API error",
#                 )

#             logger.error(
#                 "Pesapal API error: HTTP %s - %s",
#                 response.status_code,
#                 data,
#             )

#             raise PesapalError(message)

#         return data

#     # ---------------------------------------------------------
#     # Authentication
#     # ---------------------------------------------------------

#     def authenticate(self):
#         payload = {
#             "consumer_key": self.consumer_key,
#             "consumer_secret": self.consumer_secret,
#         }
#         candidates = [f"{self.base_url}/api/Auth/RequestToken"]
#         for extra in (
#             "https://cybqa.pesapal.com/pesapalv3/api/Auth/RequestToken",
#             "https://pay.pesapal.com/v3/api/Auth/RequestToken",
#         ):
#             if extra not in candidates:
#                 candidates.append(extra)

#         last_error = "Pesapal authentication failed."
#         for url in candidates:
#             try:
#                 response = requests.post(
#                     url,
#                     json=payload,
#                     headers=self._headers(),
#                     timeout=30,
#                 )
#             except requests.RequestException as exc:
#                 last_error = "Unable to connect to Pesapal."
#                 logger.exception("Could not connect to Pesapal authentication at %s", url)
#                 continue

#             try:
#                 data = self._handle_response(response)
#             except PesapalError as exc:
#                 last_error = str(exc)
#                 continue

#             token = data.get("token")
#             if token:
#                 # Keep subsequent calls on the host that actually authenticated.
#                 if "/pesapalv3" in url:
#                     self.base_url = "https://cybqa.pesapal.com/pesapalv3"
#                 elif "pay.pesapal.com" in url:
#                     self.base_url = "https://pay.pesapal.com/v3"
#                 return token

#             error = data.get("error")
#             if isinstance(error, dict):
#                 last_error = error.get("message") or last_error
#             else:
#                 last_error = data.get("message") or last_error
#             logger.error("Pesapal auth at %s returned no token: %s", url, data)

#         raise PesapalError(last_error)

#     # ---------------------------------------------------------
#     # Register IPN
#     # ---------------------------------------------------------

#     def register_ipn(
#         self,
#         token,
#         url,
#         notification_type="GET",
#     ):
#         endpoint = (
#             f"{self.base_url}"
#             "/api/URLSetup/RegisterIPN"
#         )

#         payload = {
#             "url": url,
#             "ipn_notification_type": notification_type,
#         }

#         try:
#             response = requests.post(
#                 endpoint,
#                 json=payload,
#                 headers=self._headers(token),
#                 timeout=30,
#             )

#         except requests.RequestException as exc:
#             raise PesapalError(
#                 "Unable to register Pesapal IPN."
#             ) from exc

#         return self._handle_response(response)

#     # ---------------------------------------------------------
#     # Get IPN list
#     # ---------------------------------------------------------

#     def get_ipn_list(self, token):
#         endpoint = (
#             f"{self.base_url}"
#             "/api/URLSetup/GetIpnList"
#         )

#         try:
#             response = requests.get(
#                 endpoint,
#                 headers=self._headers(token),
#                 timeout=30,
#             )

#         except requests.RequestException as exc:
#             raise PesapalError(
#                 "Unable to retrieve Pesapal IPNs."
#             ) from exc

#         return self._handle_response(response)

#     # ---------------------------------------------------------
#     # Submit order
#     # ---------------------------------------------------------

#     def submit_order(
#         self,
#         token,
#         *,
#         reference,
#         amount,
#         currency,
#         description,
#         callback_url,
#         notification_id,
#         billing_address,
#         cancellation_url=None,
#     ):
#         endpoint = (
#             f"{self.base_url}"
#             "/api/Transactions/SubmitOrderRequest"
#         )

#         payload = {
#             "id": reference,
#             "currency": currency,
#             "amount": float(
#                 Decimal(str(amount))
#             ),
#             "description": description,
#             "callback_url": callback_url,
#             "notification_id": notification_id,
#             "billing_address": billing_address,
#         }

#         if cancellation_url:
#             payload["cancellation_url"] = (
#                 cancellation_url
#             )

#         try:
#             response = requests.post(
#                 endpoint,
#                 json=payload,
#                 headers=self._headers(token),
#                 timeout=30,
#             )

#         except requests.RequestException as exc:
#             logger.exception(
#                 "Pesapal SubmitOrderRequest failed."
#             )

#             raise PesapalError(
#                 "Unable to create Pesapal payment."
#             ) from exc

#         return self._handle_response(response)

#     # ---------------------------------------------------------
#     # Transaction status
#     # ---------------------------------------------------------

#     def get_transaction_status(
#         self,
#         token,
#         tracking_id,
#     ):
#         endpoint = (
#             f"{self.base_url}"
#             "/api/Transactions/GetTransactionStatus"
#         )

#         try:
#             response = requests.get(
#                 endpoint,
#                 params={
#                     "orderTrackingId": tracking_id,
#                 },
#                 headers=self._headers(token),
#                 timeout=30,
#             )

#         except requests.RequestException as exc:
#             logger.exception(
#                 "Pesapal status request failed."
#             )

#             raise PesapalError(
#                 "Unable to verify Pesapal payment."
#             ) from exc

#         return self._handle_response(response)

#     # ---------------------------------------------------------
#     # Cancel order
#     # ---------------------------------------------------------

#     def cancel_order(
#         self,
#         token,
#         tracking_id,
#     ):
#         endpoint = (
#             f"{self.base_url}"
#             "/api/Transactions/CancelOrder"
#         )

#         payload = {
#             "order_tracking_id": tracking_id,
#         }

#         try:
#             response = requests.post(
#                 endpoint,
#                 json=payload,
#                 headers=self._headers(token),
#                 timeout=30,
#             )

#         except requests.RequestException as exc:
#             raise PesapalError(
#                 "Unable to cancel Pesapal order."
#             ) from exc

#         return self._handle_response(response)


# class PesapalPaymentService:
#     """Service to handle PesaPal payment integration for wallet top-ups."""

#     _cached_notification_id = None

#     def __init__(self):
#         self.pesapal = PesapalClient()
#         self.token = None
#         self.token_expiry = 0

#     def _ensure_token(self, force_refresh=False):
#         """Ensure we have a valid token."""
#         current_time = time.time()
#         if self.token and not force_refresh and current_time < self.token_expiry:
#             return self.token
        
#         try:
#             self.token = self.pesapal.authenticate()
#             # Token typically lasts 1 hour, refresh after 50 minutes
#             self.token_expiry = current_time + (50 * 60)
#             return self.token
#         except PesapalError as exc:
#             logger.error("Failed to obtain PesaPal token: %s", exc)
#             raise

#     def initiate_payment(
#         self,
#         order_id: str,
#         amount: float,
#         description: str,
#         callback_url: str,
#         notification_id: str,
#         billing_address: dict,
#         customer_email: str = None,
#         customer_phone: str = None,
#     ) -> dict:
#         """
#         Initiate a PesaPal payment order.
        
#         Args:
#             order_id: Unique order reference
#             amount: Amount to pay
#             description: Payment description
#             callback_url: URL to redirect after payment
#             notification_id: PesaPal notification ID (from IPN registration)
#             billing_address: Customer billing address dict
#             customer_email: Optional customer email
#             customer_phone: Optional customer phone
            
#         Returns:
#             dict with payment URL and tracking ID
#         """
#         try:
#             token = self._ensure_token()
#             notification_id = self.resolve_notification_id(notification_id)
#             response = self.pesapal.submit_order(
#                 token,
#                 reference=order_id,
#                 amount=amount,
#                 currency="UGX",
#                 description=description,
#                 callback_url=callback_url,
#                 notification_id=notification_id,
#                 billing_address=billing_address,
#             )
            
#             return {
#                 "success": True,
#                 "order_tracking_id": response.get("order_tracking_id"),
#                 "merchant_reference": response.get("merchant_reference"),
#                 "redirect_url": response.get("redirect_url"),
#                 "status": response.get("status"),
#                 "response_data": response,
#             }
#         except PesapalError as exc:
#             logger.error("PesaPal payment initiation failed: %s", exc)
#             return {
#                 "success": False,
#                 "error": str(exc),
#             }

#     def verify_payment(self, tracking_id: str) -> dict:
#         """
#         Verify payment status from PesaPal.
        
#         Args:
#             tracking_id: Order tracking ID from PesaPal
            
#         Returns:
#             dict with payment status
#         """
#         token = self._ensure_token()
        
#         try:
#             response = self.pesapal.get_transaction_status(token, tracking_id)
#             status = map_pesapal_transaction_status(response)

#             return {
#                 "success": True,
#                 "status": status,
#                 "payment_status_description": response.get("payment_status_description"),
#                 "amount": response.get("amount"),
#                 "merchant_reference": response.get("merchant_reference"),
#                 "response_data": response,
#             }
#         except PesapalError as exc:
#             logger.error("PesaPal payment verification failed: %s", exc)
#             return {
#                 "success": False,
#                 "status": "error",
#                 "error": str(exc),
#             }

#     def public_ipn_url(self) -> str:
#         configured = (getattr(settings, "PESAPAL_IPN_URL", "") or "").strip()
#         backend = (getattr(settings, "backend_url", "") or "").rstrip("/")
#         candidate = configured or f"{backend}/api/wallet/pesapal/callback/"
#         if "localhost" in candidate or "127.0.0.1" in candidate:
#             if backend and "localhost" not in backend and "127.0.0.1" not in backend:
#                 return f"{backend}/api/wallet/pesapal/callback/"
#         return candidate

#     def resolve_notification_id(self, notification_id: Optional[str] = None) -> str:
#         placeholder_ids = {"", "1234567890", "your_notification_id_here", "your_pesapal_notification_id"}
#         candidate = (notification_id or getattr(settings, "PESAPAL_NOTIFICATION_ID", "") or "").strip()
#         if candidate and candidate not in placeholder_ids:
#             return candidate
#         if PesapalPaymentService._cached_notification_id:
#             return PesapalPaymentService._cached_notification_id

#         ipn_url = self.public_ipn_url()
#         listed = self.get_registered_ipns()
#         if listed.get("success"):
#             for item in listed.get("ipns") or []:
#                 if not isinstance(item, dict):
#                     continue
#                 url = (item.get("url") or "").rstrip("/")
#                 found = item.get("ipn_id") or item.get("id")
#                 if found and url == ipn_url.rstrip("/"):
#                     PesapalPaymentService._cached_notification_id = found
#                     return found
#             # Reuse any active registered IPN if URLs differ (localhost vs public).
#             for item in listed.get("ipns") or []:
#                 if isinstance(item, dict) and (item.get("ipn_id") or item.get("id")):
#                     found = item.get("ipn_id") or item.get("id")
#                     PesapalPaymentService._cached_notification_id = found
#                     return found

#         registered = self.register_ipn(ipn_url)
#         found = (
#             registered.get("notification_id")
#             or (registered.get("response_data") or {}).get("ipn_id")
#             or (registered.get("response_data") or {}).get("id")
#         )
#         if registered.get("success") and found:
#             PesapalPaymentService._cached_notification_id = found
#             logger.info("Registered PesaPal IPN %s for %s", found, ipn_url)
#             return found

#         raise PesapalError(
#             registered.get("error")
#             or "PesaPal notification_id is missing. Register an IPN URL in the merchant dashboard or set PESAPAL_NOTIFICATION_ID."
#         )

#     def register_ipn(self, ipn_url: str) -> dict:
#         """Register IPN URL for payment notifications."""
#         token = self._ensure_token()
        
#         try:
#             response = self.pesapal.register_ipn(token, ipn_url)
#             return {
#                 "success": True,
#                 "notification_id": response.get("ipn_id") or response.get("id"),
#                 "url": response.get("url"),
#                 "response_data": response,
#             }
#         except PesapalError as exc:
#             logger.error("Failed to register PesaPal IPN: %s", exc)
#             return {
#                 "success": False,
#                 "error": str(exc),
#             }

#     def get_registered_ipns(self) -> dict:
#         """Get list of registered IPNs."""
#         token = self._ensure_token()
        
#         try:
#             response = self.pesapal.get_ipn_list(token)
#             ipns = response
#             if isinstance(response, dict):
#                 ipns = response.get("ipns") or response.get("ipn_list") or [response]
#             return {
#                 "success": True,
#                 "ipns": ipns if isinstance(ipns, list) else [ipns],
#             }
#         except PesapalError as exc:
#             logger.error("Failed to retrieve PesaPal IPNs: %s", exc)
#             return {
#                 "success": False,
#                 "error": str(exc),
#             }   
    
# """
# Iotec Payment Service

# Raises:
#     RuntimeError: _description_
#     RuntimeError: _description_
#     RuntimeError: _description_

# Returns:
#     _type_: _description_
# """
# class IotecPaymentService:
#     """Adapter for the ioTec Pay collection endpoints used for wallet top-ups.

#     Token and payment API now live on DIFFERENT hosts, per ioTec's docs:
#     - Identity/token: id.iotec.io  (IOTEC_IDENTITY_URL)
#     - Payments API:   pay.iotec.io (IOTEC_PAY_BASE_URL)
#     Fetching the token from the payments host was the likely cause of the
#     401s -- that endpoint doesn't live there.
#     """

#     def __init__(self, base_url: Optional[str] = None, identity_url: Optional[str] = None):
#         self.base_url = base_url or getattr(settings, "IOTEC_PAY_BASE_URL", "https://pay.iotec.io")
#         self.identity_url = identity_url or getattr(settings, "IOTEC_IDENTITY_URL", "https://id.iotec.io")
#         self.client_id = getattr(settings, "IOTEC_PAY_CLIENT_ID", "")
#         self.client_secret = getattr(settings, "IOTEC_PAY_CLIENT_SECRET", "")
#         self.timeout = int(getattr(settings, "IOTEC_PAY_TIMEOUT", 20))
#         self.access_token = ""
#         self._token_expires_at = 0

#     def _headers(self) -> Dict[str, str]:
#         headers = {"Content-Type": "application/json", "Accept": "application/json"}
#         if self.access_token:
#             headers["Authorization"] = f"Bearer {self.access_token}"
#         return headers

#     def _fetch_token(self, use_basic_auth: bool) -> requests.Response:
#         """Two auth styles exist for IdentityServer-style token endpoints
#         depending on how the client is registered on ioTec's side:
#         client_secret_post (credentials in the form body) or
#         client_secret_basic (credentials as an HTTP Basic Auth header).
#         We try body-auth first, then Basic-auth if that 401s -- logging
#         both attempts fully so it's obvious which one ioTec expects."""
#         token_url = f"{self.identity_url}/connect/token"

#         data = {"grant_type": "client_credentials"}  # no scope param -- ioTec's documented example sends none; the token response returns whatever scope the client is provisioned for
#         headers = {"Content-Type": "application/x-www-form-urlencoded"}

#         if use_basic_auth:
#             credentials = base64.b64encode(f"{self.client_id}:{self.client_secret}".encode()).decode()
#             headers["Authorization"] = f"Basic {credentials}"
#         else:
#             data["client_id"] = self.client_id
#             data["client_secret"] = self.client_secret

#         resp = requests.post(token_url, data=data, headers=headers, timeout=self.timeout)
#         logger.info(
#             "ioTec token request auth_style=%s url=%s status=%s body=%s",
#             "basic" if use_basic_auth else "body", token_url, resp.status_code, resp.text[:500],
#         )
#         return resp

#     def ensure_access_token(self, force_refresh=False):
#         if self.access_token and not force_refresh and time.time() < self._token_expires_at:
#             return self.access_token

#         if not self.client_id or not self.client_secret:
#             logger.error("ioTec client credentials are not configured -- cannot fetch an access token")
#             raise RuntimeError("IOTEC_PAY_CLIENT_ID / IOTEC_PAY_CLIENT_SECRET are not set.")

#         response = self._fetch_token(use_basic_auth=False)
#         if response.status_code == 401:
#             logger.warning("ioTec token request 401'd with body-auth, retrying with Basic auth")
#             response = self._fetch_token(use_basic_auth=True)

#         if response.status_code != 200:
#             raise RuntimeError(
#                 f"ioTec token request failed with both auth styles: "
#                 f"{response.status_code} {response.text[:500]}"
#             )

#         token_payload = response.json()
#         self.access_token = token_payload.get("access_token", "")
#         if not self.access_token:
#             raise RuntimeError(f"ioTec token response had no access_token: {token_payload}")

#         expires_in = int(token_payload.get("expires_in", 300) or 300)
#         self._token_expires_at = time.time() + max(60, expires_in - 30)
#         return self.access_token

#     def _request_with_token_retry(self, method, url, **kwargs):
#         self.ensure_access_token()
#         response = requests.request(method=method, url=url, headers=self._headers(), timeout=self.timeout, **kwargs)
#         logger.info("ioTec %s %s status=%s body=%s", method, url, response.status_code, response.text[:600])

#         if response.status_code in (401, 403):
#             logger.warning("ioTec API call 401'd with existing token -- forcing token refresh and retrying once")
#             self.ensure_access_token(force_refresh=True)
#             response = requests.request(method=method, url=url, headers=self._headers(), timeout=self.timeout, **kwargs)
#             logger.info("ioTec %s %s retry status=%s body=%s", method, url, response.status_code, response.text[:600])

#         response.raise_for_status()
#         return response

#     def initiate_collection(
#         self, *, wallet_id: str, external_id: str, amount: int, phone_number: str,
#         currency: str = "UGX", description: Optional[str] = None, charge_customer: bool = True,
#     ) -> Dict[str, Any]:
#         payload = {
#             "walletId": wallet_id,
#             "externalId": external_id,
#             "category": "MobileMoney",
#             "currency": currency,
#             "payer": phone_number,
#             "amount": int(amount),
#             "payerNote": description or "YoSpaces wallet top-up",
#             "payeeNote": description or "YoSpaces wallet top-up",
#             "transactionChargesCategory": "ChargeCustomer" if charge_customer else "ChargeWallet",
#         }
#         response = self._request_with_token_retry("POST", f"{self.base_url}/api/collections/collect", json=payload)
#         data = response.json()
#         return {
#             "status": data.get("status", "Pending"),
#             "requestId": data.get("id") or data.get("requestId"),
#             "externalId": data.get("externalId") or external_id,
#             "raw": data,
#         }

#     def get_collection_status(self, *, external_id: str) -> Dict[str, Any]:
#         response = self._request_with_token_retry("GET", f"{self.base_url}/api/collections/external-id/{external_id}")
#         data = response.json()
#         return {
#             "status": data.get("status", "Pending"),
#             "requestId": data.get("id") or data.get("requestId"),
#             "externalId": data.get("externalId") or external_id,
#             "raw": data,
#         }


# def get_sms_price_ugx(network_code: str) -> int:
#     from ..models import TelecomNetwork
#     row = TelecomNetwork.objects.filter(code__iexact=network_code, is_active=True).first()
#     if row:
#         return row.selling_price_ugx
#     fallback = {
#         "MTN": settings.SMS_PRICE_MTN_UGX,
#         "AIRTEL": settings.SMS_PRICE_AIRTEL_UGX,
#     }.get(network_code.upper(), settings.SMS_PRICE_OTHER_UGX)
#     logger.warning("No active TelecomNetwork row for code=%s, using settings fallback=%s", network_code, fallback)
#     return fallback