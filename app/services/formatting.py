"""INR formatting with Indian digit grouping (lakh/crore)."""

import math


def format_inr(amount) -> str:
    """Format a number as Indian Rupees with lakh/crore grouping.

    1234 -> ₹1,234 | 100000 -> ₹1,00,000 | 12345678 -> ₹1,23,45,678
    0 -> ₹0 | -5000 -> -₹5,000 | None/NaN/garbage -> ₹0
    """
    try:
        if amount is None:
            return "₹0"
        value = float(amount)
        if math.isnan(value) or math.isinf(value):
            return "₹0"
    except (TypeError, ValueError):
        return "₹0"

    rounded = int(round(value))
    sign = "-" if rounded < 0 else ""
    digits = str(abs(rounded))

    if len(digits) <= 3:
        grouped = digits
    else:
        last3 = digits[-3:]
        rest = digits[:-3]
        parts = []
        while len(rest) > 2:
            parts.insert(0, rest[-2:])
            rest = rest[:-2]
        if rest:
            parts.insert(0, rest)
        grouped = ",".join(parts) + "," + last3

    return f"{sign}₹{grouped}"
