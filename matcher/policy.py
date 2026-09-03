"""Policy gate. The tie-check is an explicit rule, not an emergent property of argmax.

AUTO_CLOSE = policy-authorized reconciliation closure, not "a likely counterpart exists."
ESCALATE   = candidate(s) exist, evidence insufficient for automatic closure.
UNRESOLVED = no valid counterpart was established.
"""

from __future__ import annotations

from config import settings
from matcher.reasons import pick
from models import CandidateScore


def never_auto_close_on_tie(ranked: list[CandidateScore], delta: float | None = None) -> bool:
    """Return True when the top two viable candidates are too close to pick.

    AUTO_CLOSE is forbidden when this returns True — even at score 0.99.
    """
    delta = settings.tie_delta if delta is None else delta
    viable = [c for c in ranked if not c.blockers]
    if len(viable) < 2:
        return False
    return abs(viable[0].score - viable[1].score) <= delta


def _margin(ranked: list[CandidateScore]) -> float | None:
    viable = [c for c in ranked if not c.blockers]
    if len(viable) < 2:
        return None
    return round(abs(viable[0].score - viable[1].score), 4)


def apply_policy(
    invoice_ranked: list[CandidateScore],
    bank_ranked: list[CandidateScore],
) -> tuple[str, str, float, CandidateScore | None, CandidateScore | None, bool]:
    """Returns decision, reason_code, confidence, invoice pick, bank pick, is_tie."""
    inv_tie = never_auto_close_on_tie(invoice_ranked)
    bank_tie = never_auto_close_on_tie(bank_ranked)
    is_tie = inv_tie or bank_tie

    inv = next((c for c in invoice_ranked if not c.blockers), None)
    bank = next((c for c in bank_ranked if not c.blockers), None)

    fail_codes: list[str] = []
    for c in (invoice_ranked[:1] + bank_ranked[:1]):
        fail_codes.extend(c.blockers)

    if any("CURRENCY_MISMATCH" in (c.blockers or []) for c in invoice_ranked[:3] + bank_ranked[:3]):
        fail_codes.append("CURRENCY_MISMATCH")
    if any("TXN_TYPE_MISMATCH" in (c.blockers or []) for c in invoice_ranked[:3] + bank_ranked[:3]):
        fail_codes.append("TXN_TYPE_MISMATCH")
    if any("ALREADY_CONSUMED" in (c.blockers or []) for c in invoice_ranked + bank_ranked) and (inv is None or bank is None):
        fail_codes.append("DUPLICATE_CANDIDATE")

    if inv is None and bank is None:
        fail_codes.append("MISSING_COUNTERPART")
        return "unresolved", pick(fail_codes), 0.0, None, None, False
    if inv is None or bank is None:
        fail_codes.append("MISSING_COUNTERPART")
        conf = inv.score if inv else (bank.score if bank else 0.0)
        decision = "escalate" if "DUPLICATE_CANDIDATE" in fail_codes else "unresolved"
        return decision, pick(fail_codes), conf, inv, bank, False

    confidence = round(min(inv.score, bank.score), 4)

    if is_tie:
        fail_codes.append("AMBIGUOUS_CANDIDATES")
        return "escalate", pick(fail_codes), confidence, inv, bank, True

    ref_conflict = (
        inv.components.get("reference", 1.0) < 0.5
        and inv.components.get("amount", 0.0) >= 0.9
        and inv.components.get("vendor", 0.0) >= 0.8
    )
    if ref_conflict:
        fail_codes.append("REFERENCE_CONFLICT")
        return "escalate", pick(fail_codes), confidence, inv, bank, False

    if confidence >= settings.auto_close_threshold:
        return "auto_close", "HIGH_CONFIDENCE", confidence, inv, bank, False

    if inv.components.get("amount", 1.0) < 0.7 or bank.components.get("amount", 1.0) < 0.7:
        fail_codes.append("AMOUNT_VARIANCE")
        return "escalate", pick(fail_codes), confidence, inv, bank, False

    if inv.components.get("date", 1.0) == 0.0 or bank.components.get("date", 1.0) == 0.0:
        fail_codes.append("DATE_OUTSIDE_WINDOW")
        return "escalate", pick(fail_codes), confidence, inv, bank, False

    if confidence >= settings.review_threshold:
        return "escalate", "LOW_CONFIDENCE", confidence, inv, bank, False

    return "unresolved", "NO_CONFIDENT_MATCH", confidence, inv, bank, False


def proof_payload(
    *,
    decision: str,
    reason: str,
    confidence: float,
    inv: CandidateScore | None,
    bank: CandidateScore | None,
    inv_ranked: list[CandidateScore],
    bank_ranked: list[CandidateScore],
    is_tie: bool,
) -> dict:
    inv_margin = _margin(inv_ranked)
    bank_margin = _margin(bank_ranked)
    runner = None
    if inv_ranked:
        viable = [c for c in inv_ranked if not c.blockers]
        if len(viable) >= 2:
            runner = {"record_id": viable[1].record_id, "score": viable[1].score}
    checks = {
        "score_threshold": confidence >= settings.auto_close_threshold,
        "tie_margin": not is_tie,
        "counterpart": bool(inv and bank),
        "currency": not any("CURRENCY_MISMATCH" in c.blockers for c in (inv_ranked[:2] + bank_ranked[:2])),
        "txn_type": not any("TXN_TYPE_MISMATCH" in c.blockers for c in (inv_ranked[:2] + bank_ranked[:2])),
        "no_duplicate": not any("ALREADY_CONSUMED" in c.blockers for c in (inv_ranked[:1] + bank_ranked[:1]) if c),
    }
    kind = "PROOF_OF_CLOSURE" if decision == "auto_close" else "PROOF_OF_REFUSAL"
    return {
        "kind": kind,
        "decision": decision.upper(),
        "reason_code": reason,
        "score": confidence,
        "runner_up": runner,
        "invoice_margin": inv_margin,
        "bank_margin": bank_margin,
        "policy_checks": checks,
        "matcher_version": settings.matcher_version,
        "policy_version": settings.policy_version,
    }
