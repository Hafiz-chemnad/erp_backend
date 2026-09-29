"""Phone-number normalisation shared by POS billing and (optionally) the bot.

WhatsApp Cloud API identifies customers by full international digits with no
"+" — e.g. 919876543210. Staff type numbers many ways ("98765 43210",
"+91-98765-43210", "098765 43210"), and if the stored number doesn't match
what Meta sends back in a webhook (`msg["from"]`), two things break:
  * the "Order ready" / "Accepted" messages can't be delivered, and
  * a phone-delivery order can never be matched to the customer's location pin.
"""
import re

DEFAULT_COUNTRY_CODE = "91"


def normalize_phone(raw: str | None, default_cc: str = DEFAULT_COUNTRY_CODE) -> str:
    digits = re.sub(r"\D", "", raw or "")
    if not digits:
        return ""
    if digits.startswith("00"):          # 0091... international prefix
        digits = digits[2:]
    if len(digits) == 11 and digits.startswith("0"):   # 098765 43210 trunk prefix
        digits = digits[1:]
    if len(digits) == 10:                # bare national number
        digits = default_cc + digits
    return digits
