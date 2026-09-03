"""Evidence scoring. Weights are config — not magic numbers in the engine loop.

Amount comparisons use integer paise. Currency and txn_type are hard blockers.
"""

from __future__ import annotations

from datetime import date

from config import settings
from matcher.money import amounts_within, to_minor
from matcher.normalize import days_apart, name_similarity, reference_similarity


def date_similarity(a: date, b: date, window: int | None = None) -> float:
    window = window if window is not None else settings.date_window_days
    d = days_apart(a, b)
    if d == 0:
        return 1.0
    if d > window:
        return 0.0
    return round(0.82 + 0.18 * (1.0 - d / window), 4)


def amount_similarity(left: float, right: float, fee: float = 0.0, tax: float = 0.0) -> tuple[float, bool]:
    try:
        left_m = to_minor(left)
        right_m = to_minor(right)
        fee_m = to_minor(fee)
        tax_m = to_minor(tax)
    except ValueError:
        return 0.0, False

    if abs(left_m - right_m) <= 5:
        return 1.0, False
    explained = right_m - fee_m - tax_m
    if abs(left_m - explained) <= 5:
        return 0.96, True
    explained2 = left_m + fee_m + tax_m
    if abs(right_m - explained2) <= 5:
        return 0.96, True
    denom = max(abs(right_m), abs(left_m), 100)
    rel = abs(left_m - right_m) / denom
    if rel <= settings.amount_rel_tolerance:
        return max(0.0, 1.0 - rel / settings.amount_rel_tolerance) * 0.7, False
    # Beyond tolerance: fail closed. 10% drift must not still score 0.90.
    if rel >= 0.05:
        return 0.12, False
    return max(0.0, 0.45 - rel * 4), False


def score_pair(
    *,
    reference_a: str,
    reference_b: str,
    amount_a: float,
    amount_b: float,
    vendor_a: str,
    vendor_b: str,
    date_a: date,
    date_b: date,
    fee: float = 0.0,
    tax: float = 0.0,
    currency_a: str = "INR",
    currency_b: str = "INR",
    txn_type_a: str = "PAYMENT",
    txn_type_b: str = "PAYMENT",
) -> tuple[float, dict[str, float], list[str], bool]:
    blockers: list[str] = []
    if (currency_a or "INR").upper() != (currency_b or "INR").upper():
        blockers.append("CURRENCY_MISMATCH")
    ta = (txn_type_a or "PAYMENT").upper()
    tb = (txn_type_b or "PAYMENT").upper()
    if ta != tb:
        blockers.append("TXN_TYPE_MISMATCH")

    ref = reference_similarity(reference_a, reference_b)
    amt, fee_ok = amount_similarity(amount_a, amount_b, fee, tax)
    ven = name_similarity(vendor_a, vendor_b)
    dt = date_similarity(date_a, date_b)

    score = (
        settings.score_w_reference * ref
        + settings.score_w_amount * amt
        + settings.score_w_vendor * ven
        + settings.score_w_date * dt
    )
    components = {
        "reference": round(ref, 4),
        "amount": round(amt, 4),
        "vendor": round(ven, 4),
        "date": round(dt, 4),
        "weighted": round(score, 4),
    }
    if blockers:
        return 0.0, components, blockers, fee_ok
    return round(score, 4), components, blockers, fee_ok
