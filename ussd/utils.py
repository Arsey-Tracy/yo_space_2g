def _normalize_phone(phone: str) -> str:
    """Normalise a phone number to E.164 (+256...) format."""
    phone = (phone or "").strip().replace(" ", "")
    if not phone:
        return phone
    if phone.startswith("+"):
        return phone
    if phone.startswith("0"):
        return "+256" + phone[1:]
    return "+" + phone
