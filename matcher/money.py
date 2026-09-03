"""Integer minor-unit arithmetic. Policy never compares raw floats for money."""

from __future__ import annotations

import math
from decimal import Decimal, InvalidOperation, ROUND_HALF_EVEN

SCALE = Decimal("100")  # paise / cents
MAX_MINOR = 10**15  # guardrail against overflow / Infinity


def to_minor(value: object) -> int:
    """Convert a rupee/dollar amount to integer minor units (paise)."""
    if value is None:
        raise ValueError("INVALID_AMOUNT")
    if isinstance(value, bool):
        raise ValueError("INVALID_AMOUNT")
    if isinstance(value, float) and (math.isnan(value) or math.isinf(value)):
        raise ValueError("INVALID_AMOUNT")
    try:
        d = Decimal(str(value)).quantize(Decimal("0.01"), rounding=ROUND_HALF_EVEN)
    except (InvalidOperation, ValueError, TypeError) as exc:
        raise ValueError("INVALID_AMOUNT") from exc
    minor = int(d * SCALE)
    if abs(minor) > MAX_MINOR:
        raise ValueError("AMOUNT_OVERFLOW")
    return minor


def from_minor(minor: int) -> float:
    return float(Decimal(minor) / SCALE)


def amounts_within(a: object, b: object, tol_minor: int = 5) -> bool:
    """True when |a-b| <= tol_minor paise (default 5 paise = ₹0.05)."""
    try:
        return abs(to_minor(a) - to_minor(b)) <= tol_minor
    except ValueError:
        return False


def validate_amount(value: object, *, allow_zero: bool = False) -> int:
    minor = to_minor(value)
    if minor < 0:
        raise ValueError("NEGATIVE_AMOUNT")
    if minor == 0 and not allow_zero:
        raise ValueError("ZERO_AMOUNT")
    return minor


def sanitize_export_cell(value: object) -> str:
    """Neutralize spreadsheet formula injection on CSV export."""
    s = "" if value is None else str(value)
    s = s.replace("\r", " ").replace("\n", " ").replace("\t", " ")
    if s[:1] in {"=", "+", "-", "@", "|", "\t"}:
        return "'" + s
    return s
