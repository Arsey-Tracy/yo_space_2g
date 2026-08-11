import base64
import logging
import time
from typing import Any, Dict, Optional

import requests
from django.conf import settings

logger = logging.getLogger(__name__)


class IotecPaymentService:
    """Adapter for the ioTec Pay collection endpoints used for wallet top-ups.

    Token and payment API now live on DIFFERENT hosts, per ioTec's docs:
    - Identity/token: id.iotec.io  (IOTEC_IDENTITY_URL)
    - Payments API:   pay.iotec.io (IOTEC_PAY_BASE_URL)
    Fetching the token from the payments host was the likely cause of the
    401s -- that endpoint doesn't live there.
    """

    def __init__(self, base_url: Optional[str] = None, identity_url: Optional[str] = None):
        self.base_url = base_url or getattr(settings, "IOTEC_PAY_BASE_URL", "https://pay.iotec.io")
        self.identity_url = identity_url or getattr(settings, "IOTEC_IDENTITY_URL", "https://id.iotec.io")
        self.client_id = getattr(settings, "IOTEC_PAY_CLIENT_ID", "")
        self.client_secret = getattr(settings, "IOTEC_PAY_CLIENT_SECRET", "")
        self.timeout = int(getattr(settings, "IOTEC_PAY_TIMEOUT", 20))
        self.access_token = ""
        self._token_expires_at = 0

    def _headers(self) -> Dict[str, str]:
        headers = {"Content-Type": "application/json", "Accept": "application/json"}
        if self.access_token:
            headers["Authorization"] = f"Bearer {self.access_token}"
        return headers

    def _fetch_token(self, use_basic_auth: bool) -> requests.Response:
        """Two auth styles exist for IdentityServer-style token endpoints
        depending on how the client is registered on ioTec's side:
        client_secret_post (credentials in the form body) or
        client_secret_basic (credentials as an HTTP Basic Auth header).
        We try body-auth first, then Basic-auth if that 401s -- logging
        both attempts fully so it's obvious which one ioTec expects."""
        token_url = f"{self.identity_url}/connect/token"

        data = {"grant_type": "client_credentials"}  # no scope param -- ioTec's documented example sends none; the token response returns whatever scope the client is provisioned for
        headers = {"Content-Type": "application/x-www-form-urlencoded"}

        if use_basic_auth:
            credentials = base64.b64encode(f"{self.client_id}:{self.client_secret}".encode()).decode()
            headers["Authorization"] = f"Basic {credentials}"
        else:
            data["client_id"] = self.client_id
            data["client_secret"] = self.client_secret

        resp = requests.post(token_url, data=data, headers=headers, timeout=self.timeout)
        logger.info(
            "ioTec token request auth_style=%s url=%s status=%s body=%s",
            "basic" if use_basic_auth else "body", token_url, resp.status_code, resp.text[:500],
        )
        return resp

    def ensure_access_token(self, force_refresh=False):
        if self.access_token and not force_refresh and time.time() < self._token_expires_at:
            return self.access_token

        if not self.client_id or not self.client_secret:
            logger.error("ioTec client credentials are not configured -- cannot fetch an access token")
            raise RuntimeError("IOTEC_PAY_CLIENT_ID / IOTEC_PAY_CLIENT_SECRET are not set.")

        response = self._fetch_token(use_basic_auth=False)
        if response.status_code == 401:
            logger.warning("ioTec token request 401'd with body-auth, retrying with Basic auth")
            response = self._fetch_token(use_basic_auth=True)

        if response.status_code != 200:
            raise RuntimeError(
                f"ioTec token request failed with both auth styles: "
                f"{response.status_code} {response.text[:500]}"
            )

        token_payload = response.json()
        self.access_token = token_payload.get("access_token", "")
        if not self.access_token:
            raise RuntimeError(f"ioTec token response had no access_token: {token_payload}")

        expires_in = int(token_payload.get("expires_in", 300) or 300)
        self._token_expires_at = time.time() + max(60, expires_in - 30)
        return self.access_token

    def _request_with_token_retry(self, method, url, **kwargs):
        self.ensure_access_token()
        response = requests.request(method=method, url=url, headers=self._headers(), timeout=self.timeout, **kwargs)
        logger.info("ioTec %s %s status=%s body=%s", method, url, response.status_code, response.text[:600])

        if response.status_code in (401, 403):
            logger.warning("ioTec API call 401'd with existing token -- forcing token refresh and retrying once")
            self.ensure_access_token(force_refresh=True)
            response = requests.request(method=method, url=url, headers=self._headers(), timeout=self.timeout, **kwargs)
            logger.info("ioTec %s %s retry status=%s body=%s", method, url, response.status_code, response.text[:600])

        response.raise_for_status()
        return response

    def initiate_collection(
        self, *, wallet_id: str, external_id: str, amount: int, phone_number: str,
        currency: str = "UGX", description: Optional[str] = None, charge_customer: bool = True,
    ) -> Dict[str, Any]:
        payload = {
            "walletId": wallet_id,
            "externalId": external_id,
            "category": "MobileMoney",
            "currency": currency,
            "payer": phone_number,
            "amount": int(amount),
            "payerNote": description or "YoSpaces wallet top-up",
            "payeeNote": description or "YoSpaces wallet top-up",
            "transactionChargesCategory": "ChargeCustomer" if charge_customer else "ChargeWallet",
        }
        response = self._request_with_token_retry("POST", f"{self.base_url}/api/collections/collect", json=payload)
        data = response.json()
        return {
            "status": data.get("status", "Pending"),
            "requestId": data.get("id") or data.get("requestId"),
            "externalId": data.get("externalId") or external_id,
            "raw": data,
        }

    def get_collection_status(self, *, external_id: str) -> Dict[str, Any]:
        response = self._request_with_token_retry("GET", f"{self.base_url}/api/collections/external-id/{external_id}")
        data = response.json()
        return {
            "status": data.get("status", "Pending"),
            "requestId": data.get("id") or data.get("requestId"),
            "externalId": data.get("externalId") or external_id,
            "raw": data,
        }


def get_sms_price_ugx(network_code: str) -> int:
    from .models import TelecomNetwork
    row = TelecomNetwork.objects.filter(code__iexact=network_code, is_active=True).first()
    if row:
        return row.selling_price_ugx
    fallback = {
        "MTN": settings.SMS_PRICE_MTN_UGX,
        "AIRTEL": settings.SMS_PRICE_AIRTEL_UGX,
    }.get(network_code.upper(), settings.SMS_PRICE_OTHER_UGX)
    logger.warning("No active TelecomNetwork row for code=%s, using settings fallback=%s", network_code, fallback)
    return fallback