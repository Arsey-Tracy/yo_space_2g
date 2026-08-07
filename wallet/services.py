import logging
import os
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

    def _headers(self) -> Dict[str, str]:
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json",
        }
        if self.access_token:
            headers["Authorization"] = f"Bearer {self.access_token}"
        return headers

    def ensure_access_token(self) -> str:
        if self.access_token:
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
        return self.access_token

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
        response = requests.post(
            f"{self.base_url}/api/collections/collect",
            json=payload,
            headers=self._headers(),
            timeout=self.timeout,
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
        response = requests.get(
            f"{self.base_url}/api/collections/external-id/{external_id}",
            headers=self._headers(),
            timeout=self.timeout,
        )
        response.raise_for_status()
        payload = response.json()

        return {
            "status": payload.get("status") or payload.get("transactionStatus") or "Pending",
            "requestId": payload.get("requestId") or payload.get("id"),
            "externalId": payload.get("externalId") or external_id,
            "raw": payload,
        }
