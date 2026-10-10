import re


def normalize_phone(raw: str) -> str | None:
    """-> E.164 (+91 assumed for bare Indian numbers) or None when it cannot be a valid number."""
    s = re.sub(r"[\s\-().]", "", str(raw or ""))
    if not s:
        return None
    if s.startswith("00"):
        s = "+" + s[2:]
    if s.startswith("+"):
        return s if re.fullmatch(r"\+[1-9]\d{9,14}", s) else None
    if re.fullmatch(r"0?[6-9]\d{9}", s):
        return "+91" + s[-10:]
    if re.fullmatch(r"91[6-9]\d{9}", s):
        return "+" + s
    return None


def mask_phone(p: str) -> str:
    return p[:3] + "•" * max(0, len(p) - 6) + p[-3:] if len(p) > 6 else p
