def _normalize_phone(phone: str) -> str:
    phone = (phone or "").strip().replace(" ", "")
    if not phone:
        return phone
    if phone.startswith("+"):
        return phone
    if phone.startswith("0"):
        return "+256" + phone[1:]
    return "+" + phone


def normalize_phone_numbers(phone_numbers: list[str]) -> list[str]:
    """Return unique recipient numbers in the provider's normalized format."""
    return sorted(
        {
            normalized
            for phone in phone_numbers
            if (normalized := _normalize_phone(phone))
        }
    )
