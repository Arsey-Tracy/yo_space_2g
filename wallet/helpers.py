from django.conf import settings

def compute_purchase_credits(amount_ugx):
    if amount_ugx <= 0:
        return 0
    return max(1, int(amount_ugx / getattr(settings, "SMS_PRICE_OTHER_UGX", 100)))


def normalize_phone_number(phone: str) -> str:
    digits = "".join(ch for ch in (phone or "") if ch.isdigit())
    if digits.startswith("0") and len(digits) == 10:
        return "256" + digits[1:]
    return digits

def normalize_phone_number_e164(phone: str) -> str:
    """Format phone numbers into standard E.164 (+256...) required by MarzPay."""
    digits = "".join(ch for ch in (phone or "") if ch.isdigit())
    if digits.startswith("0") and len(digits) == 10:
        return "+256" + digits[1:]
    if digits.startswith("256") and len(digits) == 12:
        return "+" + digits
    if not phone.startswith("+") and digits:
        return "+" + digits
    return phone

