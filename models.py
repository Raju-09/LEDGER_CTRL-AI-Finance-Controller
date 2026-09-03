"""Canonical record shapes. Ground-truth labels never travel with matcher inputs."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Any, Optional


CORRUPTION_TYPES = (
    "exact",
    "date_shift",
    "amount_delta",
    "vendor_variation",
    "duplicate",
    "orphan",
    "ambiguous_twin",
    "partial",
    "reference_drift",
    "currency_mismatch",
    "refund",
    "conflict",
    "prompt_injection",
)


@dataclass
class Settlement:
    settlement_id: str
    amount: float
    currency: str
    date: date
    vendor_name_raw: str
    reference_id: str
    fee: float
    tax: float
    batch_id: str
    invoice_number: str = ""
    txn_type: str = "PAYMENT"


@dataclass
class BankStatement:
    txn_id: str
    amount: float
    date: date
    narration_raw: str
    reference: str
    currency: str = "INR"
    batch_id: str = ""
    txn_type: str = "PAYMENT"


@dataclass
class Invoice:
    invoice_id: str
    amount: float
    currency: str
    due_date: date
    vendor_name_raw: str
    invoice_number: str
    batch_id: str = ""
    txn_type: str = "PAYMENT"


@dataclass
class GroundTruthRow:
    true_group_id: str
    settlement_id: str
    invoice_id: Optional[str]
    bank_txn_id: Optional[str]
    corruption: str
    notes: str = ""


@dataclass
class CandidateScore:
    record_id: str
    score: float
    match_type: str
    components: dict[str, float]
    blockers: list[str] = field(default_factory=list)
    fee_explained: bool = False


@dataclass
class Decision:
    settlement_id: str
    invoice_id: Optional[str]
    bank_txn_id: Optional[str]
    match_type: str
    confidence: float
    decision: str  # auto_close | escalate | unresolved
    reason_code: str
    evidence: dict[str, Any]
    invoice_candidates: list[CandidateScore]
    bank_candidates: list[CandidateScore]
    llm_suggestion: Optional[dict[str, Any]] = None
    amount: float = 0.0
    currency: str = "INR"
    txn_type: str = "PAYMENT"
