from unittest.mock import patch

from django.test import TestCase

from wallet.services import IotecPaymentService
from wallet.views import compute_purchase_credits


class IotecPaymentServiceTests(TestCase):
    def test_compute_purchase_credits_for_custom_amount(self):
        self.assertEqual(compute_purchase_credits(4000), 100)
        self.assertEqual(compute_purchase_credits(2500), 62)

    def test_initiate_collection_returns_provider_payload(self):
        class DummyResponse:
            def __init__(self, payload, status_code=200):
                self._payload = payload
                self.status_code = status_code

            def json(self):
                return self._payload

            def raise_for_status(self):
                return None

        with patch("wallet.services.requests.post") as mocked_post:
            mocked_post.return_value = DummyResponse({
                "status": "Pending",
                "requestId": "req_123",
                "externalId": "ext_123",
            })

            service = IotecPaymentService()
            result = service.initiate_collection(
                wallet_id="wallet-1",
                external_id="ext_123",
                amount=5000,
                phone_number="0772000000",
                currency="UGX",
            )

        self.assertEqual(result["status"], "Pending")
        self.assertEqual(result["requestId"], "req_123")
        self.assertEqual(result["externalId"], "ext_123")

    def test_get_collection_status_normalizes_success_state(self):
        class DummyResponse:
            def __init__(self, payload, status_code=200):
                self._payload = payload
                self.status_code = status_code

            def json(self):
                return self._payload

            def raise_for_status(self):
                return None

        with patch("wallet.services.requests.get") as mocked_get:
            mocked_get.return_value = DummyResponse({
                "status": "Success",
                "requestId": "req_456",
                "externalId": "ext_456",
            })

            service = IotecPaymentService()
            result = service.get_collection_status(external_id="ext_456")

        self.assertEqual(result["status"], "Success")
        self.assertEqual(result["externalId"], "ext_456")

    def test_fetches_access_token_when_missing(self):
        class DummyResponse:
            def __init__(self, payload, status_code=200):
                self._payload = payload
                self.status_code = status_code

            def json(self):
                return self._payload

            def raise_for_status(self):
                return None

        def fake_post(url, data=None, json=None, headers=None, timeout=None):
            if url.endswith("/connect/token"):
                return DummyResponse({
                    "access_token": "token-123",
                    "expires_in": 300,
                    "token_type": "Bearer",
                })
            if url.endswith("/api/collections/collect"):
                return DummyResponse({
                    "status": "Pending",
                    "requestId": "req_789",
                    "externalId": "ext_789",
                })
            raise AssertionError(url)

        with patch("wallet.services.requests.post", side_effect=fake_post):
            service = IotecPaymentService(access_token=None)
            service.client_id = "client-id"
            service.client_secret = "client-secret"
            result = service.initiate_collection(
                wallet_id="wallet-1",
                external_id="ext_789",
                amount=5000,
                phone_number="0772000000",
            )

        self.assertEqual(service.access_token, "token-123")
        self.assertEqual(result["requestId"], "req_789")
