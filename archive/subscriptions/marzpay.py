import uuid
import logging
import base64
import requests
# pyrefly: ignore [missing-import]
from django.conf import settings

logger = logging.getLogger(__name__)


def trigger_marzpay_collection(phone_number: str, amount: int = 1000, description: str = "Yo-Spaces Test Payment", reference: str = None):
    """
    Sends a Mobile Money collection request to MarzPay API.
    Endpoint: https://wallet.wearemarz.com/api/v1/collect-money
    """
    collect_url = getattr(settings, 'MARZPAY_COLLECT_URL', 'https://wallet.wearemarz.com/api/v1/collect-money')
    
    api_key = getattr(settings, 'MARZPAY_API_KEY', 'marz_XSdy2ucLiJxdNkvx')
    api_secret = getattr(settings, 'MARZPAY_API_SECRET', '6iOsdoqTuJ9yzCKchuI6cTAdB8GwsRVp')
    
    # Guarantee proper RFC 7617 base64 encoding
    auth_header = base64.b64encode(f"{api_key}:{api_secret}".encode('utf-8')).decode('utf-8')

    if not reference:
        reference = str(uuid.uuid4())

    # Format phone number ensuring country code (e.g. +256...)
    formatted_phone = phone_number.strip() if phone_number else ""
    if formatted_phone:
        if not formatted_phone.startswith('+'):
            if formatted_phone.startswith('0'):
                formatted_phone = '+256' + formatted_phone[1:]
            elif formatted_phone.startswith('256'):
                formatted_phone = '+' + formatted_phone
            else:
                formatted_phone = '+256' + formatted_phone

    headers = {
        'Authorization': f'Basic {auth_header}',
        'Content-Type': 'application/json',
    }

    payload = {
        'phone_number': formatted_phone,
        'amount': str(amount),
        'country': 'UG',
        'reference': reference,
        'description': description[:255] if description else "Test Payment",
    }

    logger.info(f"Triggering MarzPay collection for {formatted_phone}, amount={amount}, ref={reference}")

    try:
        response = requests.post(collect_url, json=payload, headers=headers, timeout=15)
        try:
            response_data = response.json()
        except Exception:
            response_data = {'text': response.text}

        is_success = response.status_code in [200, 201] or (
            isinstance(response_data, dict) and response_data.get('status') in ['success', 'pending', True]
        )

        return {
            'status_code': response.status_code,
            'success': is_success,
            'reference': reference,
            'amount': amount,
            'phone_number': formatted_phone,
            'data': response_data,
        }
    except Exception as e:
        logger.error(f"Error calling MarzPay API: {e}")
        return {
            'status_code': 500,
            'success': False,
            'reference': reference,
            'amount': amount,
            'phone_number': formatted_phone,
            'error': str(e)
        }

