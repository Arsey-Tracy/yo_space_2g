"""
MarzPay service wrapper using direct HTTP API calls (no SDK required).
"""

import base64
import logging

import requests

from typing import Any, Dict, Optional
from django.conf import settings

logger = logging.getLogger(__name__)


class MarzpayError(Exception):
    """Custom exception for wallet layer."""
    pass


class MarzpayService:
    def __init__(self):
        self.api_key = getattr(settings, "MARZPAY_API_KEY", "")
        self.api_secret = getattr(settings, "MARZPAY_API_SECRET", "")
        self.base_url = "https://wallet.wearemarz.com/api/v1"
        self.callback_url = getattr(settings, "MARZPAY_CALLBACK_URL", "")
        self.timeout = 30

    def _auth_header(self) -> str:
        credentials = f"{self.api_key}:{self.api_secret}"
        encoded = base64.b64encode(credentials.encode()).decode()
        return f"Basic {encoded}"

    def _headers(self) -> dict:
        return {
            "Authorization": self._auth_header(),
            "Content-Type": "application/json",
            "Accept": "application/json",
        }

    def initiate_collection(self, amount: int, phone_number: str, reference: str,
                            description: str, callback_url: str = None):
        """Initiate a mobile-money collection via MarzPay API.

        Args:
            amount: Amount in UGX.
            phone_number: Customer phone number in E.164 format.
            reference: Unique reference for the transaction (UUID v4).
            description: Human-readable description.
            callback_url: Optional URL MarzPay will call when the transaction
                completes. Falls back to the project setting ``MARZPAY_CALLBACK_URL``.

        Returns:
            The parsed JSON response from MarzPay.
        """
        payload = {
            "amount": int(amount),
            "phone_number": phone_number,
            "reference": reference,
            "country": "UG",
            "description": description,
            "callback_url": callback_url or self.callback_url,
        }
        try:
            response = requests.post(
                f"{self.base_url}/collect-money",
                json=payload,
                headers=self._headers(),
                timeout=self.timeout,
            )
            response.raise_for_status()
            return response.json()
        except requests.RequestException as exc:
            logger.error("MarzPay collection request failed: %s", exc)
            raise MarzpayError(str(exc))

    def get_transaction_status(self, transaction_uuid: str):
        """Retrieve the status of a transaction using the MarzPay API.

        Args:
            transaction_uuid: The UUID returned by ``initiate_collection``.

        Returns:
            The transaction status payload.
        """
        try:
            response = requests.get(
                f"{self.base_url}/collect-money/{transaction_uuid}",
                headers=self._headers(),
                timeout=self.timeout,
            )
            response.raise_for_status()
            return response.json()
        except requests.RequestException as exc:
            logger.error("MarzPay status request failed for %s: %s", transaction_uuid, exc)
            raise MarzpayError(str(exc))