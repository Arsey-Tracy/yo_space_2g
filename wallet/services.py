import logging
import os
import time
from typing import Any, Dict, Optional

import requests
from django.conf import settings

logger = logging.getLogger(__name__)


class IotecPaymentService:
    """Adapter for the ioTec Pay collection endpoints used for wallet top-ups."""

    def __init__(self, base_url: Optional[str] = None, access_token: Optional[str] = None):
        self.base_url = base_url or getattr(settings, "IOTEC_PAY_BASE_URL", "https://pay.iotec.io")
        self.access_token = access_token or getattr(settings, "IOTEC_PAY_ACCESS_TOKEN", "")
        self.client_id = getattr(settings, "IOTEC_PAY_CLIENT_ID", "")
        self.client_secret = getattr(settings, "IOTEC_PAY_CLIENT_SECRET", "")
        self.timeout = int(getattr(settings, "IOTEC_PAY_TIMEOUT", 20))
        self._token_expires_at = 0

    def _headers(self) -> Dict[str, str]:
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json",
        }
        if self.access_token:
            headers["Authorization"] = f"Bearer {self.access_token}"
        return headers

    def ensure_access_token(self, force_refresh=False):
        if self.access_token and not force_refresh and time.time() < self._token_expires_at:
            return self.access_token

        if not self.client_id or not self.client_secret:
            logger.warning("ioTec client credentials are not configured; continuing without an access token")
            return ""

        token_response = requests.post(
            f"{self.base_url}/connect/token",
            data={
                "client_id": self.client_id,
                "client_secret": self.client_secret,
                "grant_type": "client_credentials",
            },
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            timeout=self.timeout,
        )
        token_response.raise_for_status()
        token_payload = token_response.json()
        self.access_token = token_payload.get("access_token", "")
        expires_in = int(token_payload.get("expires_in", 300) or 300)
        self._token_expires_at = time.time() + max(60, expires_in - 30)
        return self.access_token

    def _request_with_token_retry(self, method, url, **kwargs):
        try:
            self.ensure_access_token()
            response = requests.request(method=method, url=url, headers=self._headers(), timeout=self.timeout, **kwargs)
            response.raise_for_status()
            return response
        except requests.HTTPError as exc:
            status_code = getattr(getattr(exc, "response", None), "status_code", None)
            if status_code in {401, 403}:
                self.ensure_access_token(force_refresh=True)
                response = requests.request(method=method, url=url, headers=self._headers(), timeout=self.timeout, **kwargs)
                response.raise_for_status()
                return response
            raise

    def initiate_collection(
        self,
        *,
        wallet_id: str,
        external_id: str,
        amount: int,
        phone_number: str,
        currency: str = "UGX",
        description: Optional[str] = None,
    ) -> Dict[str, Any]:
        payload = {
            "walletId": wallet_id,
            "externalId": external_id,
            "category": "MobileMoney",
            "currency": currency,
            "payee": phone_number,
            "amount": int(amount),
            "payerNote": description or "Yo-Spaces wallet top-up",
            "payeeNote": description or "Yo-Spaces wallet top-up",
        }

        self.ensure_access_token()
        response = self._request_with_token_retry(
            "POST", f"{self.base_url}/api/collections/collect", json=payload
        )
        response.raise_for_status()
        payload = response.json()

        return {
            "status": payload.get("status") or payload.get("transactionStatus") or "Pending",
            "requestId": payload.get("requestId") or payload.get("id"),
            "externalId": payload.get("externalId") or external_id,
            "raw": payload,
        }

    def get_collection_status(self, *, external_id: str) -> Dict[str, Any]:
        self.ensure_access_token()
        response = self._request_with_token_retry(
            "GET", f"{self.base_url}/api/collections/external-id/{external_id}"
        )
        response.raise_for_status()
        payload = response.json()

        return {
            "status": payload.get("status") or payload.get("transactionStatus") or "Pending",
            "requestId": payload.get("requestId") or payload.get("id"),
            "externalId": payload.get("externalId") or external_id,
            "raw": payload,
        }
