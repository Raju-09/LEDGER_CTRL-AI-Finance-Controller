from __future__ import annotations

import re
import unicodedata
from datetime import date
from rapidfuzz import fuzz


_LEGAL = re.compile(
    r"\b(private limited|pvt\.?\s*ltd\.?|pvt ltd|ltd\.?|limited|inc\.?|llp|opc)\b",
    re.I,
)
_NON_ALNUM = re.compile(r"[^a-z0-9\s]")
_WS = re.compile(r"\s+")


def normalize_name(raw: str) -> str:
    s = unicodedata.normalize("NFKC", raw or "").lower()
    s = s.replace("&", " and ")
    s = _LEGAL.sub(" ", s)
    s = _NON_ALNUM.sub(" ", s)
    return _WS.sub(" ", s).strip()


def normalize_reference(raw: str) -> str:
    s = unicodedata.normalize("NFKC", raw or "").upper()
    return re.sub(r"[^A-Z0-9]", "", s)


def parse_amount(value: object) -> float:
    if isinstance(value, (int, float)):
        return round(float(value), 2)
    s = str(value).strip().replace("₹", "").replace(",", "").replace(" ", "")
    return round(float(s), 2)


def days_apart(a: date, b: date) -> int:
    return abs((a - b).days)


def name_similarity(a: str, b: str) -> float:
    na, nb = normalize_name(a), normalize_name(b)
    if not na or not nb:
        return 0.0
    if na == nb:
        return 1.0
    return fuzz.token_sort_ratio(na, nb) / 100.0


def reference_similarity(a: str, b: str) -> float:
    na, nb = normalize_reference(a), normalize_reference(b)
    if not na or not nb:
        return 0.0
    if na == nb:
        return 1.0
    if na in nb or nb in na:
        return 0.92
    return fuzz.ratio(na, nb) / 100.0
