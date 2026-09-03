"""Deterministic reason-code vocabulary and precedence.

Same input → same reason. The LLM never selects these codes.
"""

from __future__ import annotations

REASON_CODES = (
    "CURRENCY_MISMATCH",
    "TXN_TYPE_MISMATCH",
    "AMBIGUOUS_CANDIDATES",
    "DUPLICATE_CANDIDATE",
    "REFERENCE_CONFLICT",
    "AMOUNT_VARIANCE",
    "DATE_OUTSIDE_WINDOW",
    "UNSUPPORTED_PARTIAL",
    "MISSING_COUNTERPART",
    "LOW_CONFIDENCE",
    "NO_CONFIDENT_MATCH",
    "HIGH_CONFIDENCE",
    "PARTIAL_PAYMENT",
    "INVALID_AMOUNT",
)

# First matching code wins. Fail-closed conditions outrank confidence.
PRECEDENCE = (
    "INVALID_AMOUNT",
    "CURRENCY_MISMATCH",
    "TXN_TYPE_MISMATCH",
    "AMBIGUOUS_CANDIDATES",
    "DUPLICATE_CANDIDATE",
    "REFERENCE_CONFLICT",
    "AMOUNT_VARIANCE",
    "DATE_OUTSIDE_WINDOW",
    "UNSUPPORTED_PARTIAL",
    "MISSING_COUNTERPART",
    "LOW_CONFIDENCE",
    "NO_CONFIDENT_MATCH",
    "PARTIAL_PAYMENT",
    "HIGH_CONFIDENCE",
)

# Legacy aliases kept so older audit rows still render.
ALIASES = {
    "AMBIGUOUS": "AMBIGUOUS_CANDIDATES",
    "DUPLICATE": "DUPLICATE_CANDIDATE",
    "NO_CANDIDATE": "MISSING_COUNTERPART",
    "AMOUNT_MISMATCH": "AMOUNT_VARIANCE",
}


def canonical(code: str) -> str:
    code = (code or "").upper()
    return ALIASES.get(code, code)


def pick(codes: list[str]) -> str:
    ranked = {canonical(c): i for i, c in enumerate(PRECEDENCE)}
    present = [canonical(c) for c in codes if canonical(c) in ranked]
    if not present:
        return "NO_CONFIDENT_MATCH"
    return min(present, key=lambda c: ranked[c])
