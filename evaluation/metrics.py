"""Holdout metrics vs hidden ground truth. Matcher never imports this during scoring."""

from __future__ import annotations

from matcher.money import from_minor, to_minor
from models import Decision, GroundTruthRow

# Auto-closing these is always a false match, even if IDs coincide.
UNSAFE_TO_CLOSE = {"duplicate", "orphan", "currency_mismatch", "refund"}


def evaluate(decisions: list[Decision], truth: list[GroundTruthRow]) -> dict:
    by_sid = {t.settlement_id: t for t in truth}
    n = len(decisions)
    auto = [d for d in decisions if d.decision == "auto_close"]
    esc = [d for d in decisions if d.decision == "escalate"]
    unr = [d for d in decisions if d.decision == "unresolved"]

    true_matchable = [
        t
        for t in truth
        if t.invoice_id and t.bank_txn_id and t.corruption not in UNSAFE_TO_CLOSE
    ]
    correct_auto = []
    false_auto = []
    for d in auto:
        t = by_sid.get(d.settlement_id)
        if not t:
            false_auto.append({"settlement_id": d.settlement_id, "why": "no_ground_truth"})
            continue
        if t.corruption in UNSAFE_TO_CLOSE:
            false_auto.append(
                {
                    "settlement_id": d.settlement_id,
                    "why": f"auto_closed_{t.corruption}",
                    "predicted_invoice": d.invoice_id,
                    "true_invoice": t.invoice_id,
                }
            )
            continue
        inv_ok = d.invoice_id == t.invoice_id
        bank_ok = d.bank_txn_id == t.bank_txn_id
        if inv_ok and bank_ok:
            correct_auto.append(d.settlement_id)
        else:
            false_auto.append(
                {
                    "settlement_id": d.settlement_id,
                    "why": "wrong_counterpart",
                    "predicted_invoice": d.invoice_id,
                    "true_invoice": t.invoice_id,
                    "predicted_bank": d.bank_txn_id,
                    "true_bank": t.bank_txn_id,
                    "corruption": t.corruption,
                }
            )

    precision = len(correct_auto) / len(auto) if auto else 0.0
    recall = len(correct_auto) / len(true_matchable) if true_matchable else 0.0
    fmr = len(false_auto) / len(auto) if auto else 0.0

    missed = [
        t.settlement_id
        for t in true_matchable
        if t.settlement_id not in correct_auto
    ]
    correct_refusals = [
        d.settlement_id
        for d in decisions
        if d.decision != "auto_close"
        and by_sid.get(d.settlement_id)
        and (
            by_sid[d.settlement_id].corruption in UNSAFE_TO_CLOSE
            or not (by_sid[d.settlement_id].invoice_id and by_sid[d.settlement_id].bank_txn_id)
            or by_sid[d.settlement_id].corruption == "ambiguous_twin"
        )
    ]

    slices: dict[str, dict] = {}
    for t in truth:
        sl = slices.setdefault(
            t.corruption,
            {"n": 0, "auto_close": 0, "escalate": 0, "unresolved": 0, "correct_auto": 0, "false_auto": 0},
        )
        sl["n"] += 1
        d = next((x for x in decisions if x.settlement_id == t.settlement_id), None)
        if not d:
            continue
        sl[d.decision] = sl.get(d.decision, 0) + 1
        if d.decision == "auto_close":
            if d.settlement_id in correct_auto:
                sl["correct_auto"] += 1
            else:
                sl["false_auto"] += 1

    twin_auto = [
        d.settlement_id
        for d in auto
        if by_sid.get(d.settlement_id) and by_sid[d.settlement_id].corruption == "ambiguous_twin"
    ]

    exception_minor = 0
    by_reason_minor: dict[str, int] = {}
    for d in decisions:
        if d.decision not in {"escalate", "unresolved"}:
            continue
        try:
            minor = to_minor(d.amount)
        except ValueError:
            minor = 0
        exception_minor += minor
        code = d.reason_code or "OTHER"
        by_reason_minor[code] = by_reason_minor.get(code, 0) + minor
    exception_value = round(from_minor(exception_minor), 2)

    return {
        "records_processed": n,
        "auto_matched": len(auto),
        "escalated": len(esc),
        "unresolved": len(unr),
        "auto_resolution_rate": round(len(auto) / n, 4) if n else 0,
        "precision": round(precision, 4),
        "recall": round(recall, 4),
        "false_match_rate": round(fmr, 4),
        "exception_rate": round((len(esc) + len(unr)) / n, 4) if n else 0,
        "exception_value": exception_value,
        "exception_value_by_reason": {k: round(from_minor(v), 2) for k, v in by_reason_minor.items()},
        "denominators": {
            "precision": "correct_auto_close / auto_close_count",
            "recall": "correct_auto_close / true_matchable",
            "false_match_rate": "wrong_auto_close / auto_close_count",
            "auto_resolution_rate": "auto_close_count / records_processed",
        },
        "true_matchable": len(true_matchable),
        "confusion": {
            "correct_auto_close": len(correct_auto),
            "wrong_auto_close": len(false_auto),
            "missed_true_matches": len(missed),
            "correct_refusals": len(correct_refusals),
        },
        "slices": slices,
        "false_matches": false_auto[:25],
        "policy_note": {
            "auto_closed_ambiguous_twins": twin_auto,
            "tie_check": "never_auto_close_on_tie is an explicit function in matcher/policy.py",
        },
        "correct_auto_ids": correct_auto[:8],
        "ground_truth": {
            "independent": True,
            "accessed_by": "evaluation/metrics.py only",
            "matcher_sees_labels": False,
        },
    }
