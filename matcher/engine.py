"""Deterministic waterfall: exact → fuzzy → policy. LLM never decides."""

from __future__ import annotations

from dataclasses import asdict

from config import settings
from matcher.normalize import days_apart, normalize_name, normalize_reference
from matcher.money import amounts_within, to_minor, validate_amount
from matcher.policy import apply_policy, never_auto_close_on_tie, proof_payload
from matcher.scoring import score_pair
from models import BankStatement, CandidateScore, Decision, Invoice, Settlement


def _vendor_from_narration(narration: str) -> str:
    return narration.replace("NEFT", "").strip()


def _score_settlement_invoice(s: Settlement, inv: Invoice) -> CandidateScore:
    score, components, blockers, fee_ok = score_pair(
        reference_a=s.invoice_number or s.reference_id,
        reference_b=inv.invoice_number,
        amount_a=s.amount,
        amount_b=inv.amount,
        vendor_a=s.vendor_name_raw,
        vendor_b=inv.vendor_name_raw,
        date_a=s.date,
        date_b=inv.due_date,
        fee=s.fee,
        tax=s.tax,
        currency_a=s.currency,
        currency_b=inv.currency,
        txn_type_a=s.txn_type,
        txn_type_b=inv.txn_type,
    )
    # invoice number vs UTR is often a weak exact — boost if invoice_number field matches
    if s.invoice_number and normalize_reference(s.invoice_number) == normalize_reference(inv.invoice_number):
        score = min(1.0, score + 0.12)
        components["invoice_number_boost"] = 0.12
        components["weighted"] = round(score, 4)

    exact = (
        normalize_reference(s.invoice_number) == normalize_reference(inv.invoice_number)
        and amounts_within(s.amount + s.fee + s.tax, inv.amount)
        and days_apart(s.date, inv.due_date) <= settings.date_window_days
        and not blockers
    )
    return CandidateScore(
        record_id=inv.invoice_id,
        score=round(score, 4),
        match_type="exact" if exact and score >= 0.9 else "fuzzy",
        components=components,
        blockers=blockers,
        fee_explained=fee_ok,
    )


def _score_settlement_bank(s: Settlement, b: BankStatement) -> CandidateScore:
    score, components, blockers, fee_ok = score_pair(
        reference_a=s.reference_id,
        reference_b=b.reference,
        amount_a=s.amount,
        amount_b=b.amount,
        vendor_a=s.vendor_name_raw,
        vendor_b=_vendor_from_narration(b.narration_raw),
        date_a=s.date,
        date_b=b.date,
        fee=0.0,
        tax=0.0,
        currency_a=s.currency,
        currency_b=b.currency,
        txn_type_a=s.txn_type,
        txn_type_b=b.txn_type,
    )
    exact = (
        normalize_reference(s.reference_id) == normalize_reference(b.reference)
        and amounts_within(s.amount, b.amount)
        and days_apart(s.date, b.date) <= settings.date_window_days
        and not blockers
    )
    return CandidateScore(
        record_id=b.txn_id,
        score=round(score, 4),
        match_type="exact" if exact else "fuzzy",
        components=components,
        blockers=blockers,
        fee_explained=fee_ok,
    )


def _block_candidates(
    settlements: list[Settlement],
    invoices: list[Invoice],
    banks: list[BankStatement],
    s: Settlement,
    consumed_invoices: set[str],
    consumed_banks: set[str],
) -> tuple[list[CandidateScore], list[CandidateScore]]:
    inv_cands: list[CandidateScore] = []
    for inv in invoices:
        same_vendor = normalize_name(s.vendor_name_raw) == normalize_name(inv.vendor_name_raw)
        close_amt = (
            abs(to_minor(s.amount) - to_minor(inv.amount)) / max(to_minor(inv.amount), 100) <= 0.25
            or amounts_within(s.amount + s.fee + s.tax, inv.amount, tol_minor=100)
        )
        close_date = days_apart(s.date, inv.due_date) <= settings.date_window_days + 4
        refish = (
            normalize_reference(s.invoice_number) == normalize_reference(inv.invoice_number)
            or normalize_reference(s.reference_id) in normalize_reference(inv.invoice_number)
        )
        if not (same_vendor or close_amt or close_date or refish):
            continue
        c = _score_settlement_invoice(s, inv)
        if inv.invoice_id in consumed_invoices:
            c.blockers.append("ALREADY_CONSUMED")
        inv_cands.append(c)

    bank_cands: list[CandidateScore] = []
    for b in banks:
        close_amt = amounts_within(s.amount, b.amount, tol_minor=max(100, int(0.05 * max(to_minor(s.amount), 100))))
        close_date = days_apart(s.date, b.date) <= settings.date_window_days + 2
        refish = normalize_reference(s.reference_id) == normalize_reference(b.reference)
        if not (close_amt or close_date or refish):
            continue
        c = _score_settlement_bank(s, b)
        if b.txn_id in consumed_banks:
            c.blockers.append("ALREADY_CONSUMED")
        bank_cands.append(c)

    inv_cands.sort(key=lambda c: c.score, reverse=True)
    bank_cands.sort(key=lambda c: c.score, reverse=True)
    return inv_cands[: settings.candidate_pool_size], bank_cands[: settings.candidate_pool_size]


def _try_partial_groups(
    leftover: list[Settlement],
    invoices: list[Invoice],
    decisions_by_sid: dict[str, Decision],
    consumed_invoices: set[str],
) -> None:
    """1 invoice → N settlements when amounts uniquely sum to the invoice (net of fees).

    Integrity note: even for partial groups we run the tie-check before marking
    AUTO_CLOSE.  The invariant is unconditional: never_auto_close_on_tie() is
    never bypassed, not even by a sum-exact match.
    """
    open_s = [s for s in leftover if decisions_by_sid[s.settlement_id].decision != "auto_close"]
    by_vendor: dict[str, list[Settlement]] = {}
    for s in open_s:
        by_vendor.setdefault(normalize_name(s.vendor_name_raw), []).append(s)

    for inv in invoices:
        if inv.invoice_id in consumed_invoices:
            continue
        pool = by_vendor.get(normalize_name(inv.vendor_name_raw), [])
        if len(pool) < 2:
            continue
        # Search 2-leg combinations only (V1; N-leg would need subset-sum + uniqueness)
        found = None
        for i, a in enumerate(pool):
            for b in pool[i + 1 :]:
                total_m = (
                    to_minor(a.amount)
                    + to_minor(b.amount)
                    + to_minor(a.fee)
                    + to_minor(b.fee)
                    + to_minor(a.tax)
                    + to_minor(b.tax)
                )
                if abs(total_m - to_minor(inv.amount)) <= 10:
                    found = (a, b)
                    break
            if found:
                break
        if not found:
            continue

        a, b = found

        # Re-score each leg against the matching invoice to get honest candidates
        # for the tie-check — we do not invent a confidence, we derive it.
        inv_cand_a = _score_settlement_invoice(a, inv)
        inv_cand_b = _score_settlement_invoice(b, inv)

        # Tie-check: use the original invoice_candidates list from each leg's decision
        # (which contains ALL ranked invoices) — not just the single re-scored cand.
        # never_auto_close_on_tie([single_cand]) always returns False (needs ≥2 viable),
        # so that was a correctness bug: partial payments bypassed the tie-check entirely.
        for s, cand in ((a, inv_cand_a), (b, inv_cand_b)):
            d = decisions_by_sid[s.settlement_id]
            orig_inv_cands = d.invoice_candidates  # full ranked list from main pass
            if never_auto_close_on_tie(orig_inv_cands):
                # Original decision had a tie in its invoice candidate pool.
                # Inherit that verdict — don't force auto_close on a partial group
                # when the individual leg was already ambiguous.
                d.decision = "escalate"
                d.reason_code = "AMBIGUOUS_CANDIDATES"
                d.evidence["partial_tie_refused"] = True
                continue
            d.invoice_id = inv.invoice_id
            d.match_type = "fuzzy"
            d.reason_code = "PARTIAL_PAYMENT"
            d.evidence["partial_group"] = [a.settlement_id, b.settlement_id]
            d.evidence["partial_invoice"] = inv.invoice_id
            d.decision = "auto_close"
            d.confidence = max(d.confidence, round(cand.score, 4))
            d.evidence["proof"] = proof_payload(
                decision=d.decision,
                reason=d.reason_code,
                confidence=d.confidence,
                inv=cand,
                bank=next((c for c in d.bank_candidates if not c.blockers), None),
                inv_ranked=d.invoice_candidates,
                bank_ranked=d.bank_candidates,
                is_tie=False,
            )

        consumed_invoices.add(inv.invoice_id)


def reconcile_batch(
    settlements: list[Settlement],
    invoices: list[Invoice],
    banks: list[BankStatement],
) -> list[Decision]:
    consumed_invoices: set[str] = set()
    consumed_banks: set[str] = set()
    decisions: list[Decision] = []
    seen_sids: set[str] = set()

    # Stable order for determinism given the same inputs
    ordered = sorted(settlements, key=lambda s: s.settlement_id)

    for s in ordered:
        if s.settlement_id in seen_sids:
            decisions.append(
                Decision(
                    settlement_id=s.settlement_id,
                    invoice_id=None,
                    bank_txn_id=None,
                    match_type="none",
                    confidence=0.0,
                    decision="escalate",
                    reason_code="DUPLICATE_CANDIDATE",
                    evidence={
                        "proof": {
                            "kind": "PROOF_OF_REFUSAL",
                            "decision": "ESCALATE",
                            "reason_code": "DUPLICATE_CANDIDATE",
                            "detail": "duplicate settlement_id in batch",
                        },
                        "vendor_name_raw": s.vendor_name_raw,
                    },
                    invoice_candidates=[],
                    bank_candidates=[],
                    amount=s.amount if isinstance(s.amount, (int, float)) else 0.0,
                    currency=s.currency,
                    txn_type=s.txn_type,
                )
            )
            continue
        seen_sids.add(s.settlement_id)
        try:
            validate_amount(s.amount)
            validate_amount(s.fee, allow_zero=True)
            validate_amount(s.tax, allow_zero=True)
        except ValueError as exc:
            decisions.append(
                Decision(
                    settlement_id=s.settlement_id,
                    invoice_id=None,
                    bank_txn_id=None,
                    match_type="none",
                    confidence=0.0,
                    decision="unresolved",
                    reason_code="INVALID_AMOUNT",
                    evidence={
                        "proof": {
                            "kind": "PROOF_OF_REFUSAL",
                            "decision": "UNRESOLVED",
                            "reason_code": "INVALID_AMOUNT",
                            "detail": str(exc),
                        },
                        "vendor_name_raw": s.vendor_name_raw,
                    },
                    invoice_candidates=[],
                    bank_candidates=[],
                    amount=s.amount if isinstance(s.amount, (int, float)) else 0.0,
                    currency=s.currency,
                    txn_type=s.txn_type,
                )
            )
            continue

        inv_cands, bank_cands = _block_candidates(
            settlements, invoices, banks, s, consumed_invoices, consumed_banks
        )
        decision, reason, conf, inv, bank, is_tie = apply_policy(inv_cands, bank_cands)

        match_type = "fuzzy"
        if inv and bank and inv.match_type == "exact" and bank.match_type == "exact":
            match_type = "exact"

        proof = proof_payload(
            decision=decision,
            reason=reason,
            confidence=conf,
            inv=inv,
            bank=bank,
            inv_ranked=inv_cands,
            bank_ranked=bank_cands,
            is_tie=is_tie,
        )
        evidence = {
            "invoice_top": [asdict(c) for c in inv_cands[:3]],
            "bank_top": [asdict(c) for c in bank_cands[:3]],
            "tie_check": is_tie,
            "tie_delta": settings.tie_delta,
            "auto_close_threshold": settings.auto_close_threshold,
            "fee": s.fee,
            "tax": s.tax,
            "vendor_name_raw": s.vendor_name_raw,
            "currency": s.currency,
            "txn_type": s.txn_type,
            "fee_explained_invoice": bool(inv.fee_explained) if inv else False,
            "proof": proof,
            "matcher_version": settings.matcher_version,
            "policy_version": settings.policy_version,
        }

        if decision == "auto_close" and inv and bank:
            consumed_invoices.add(inv.record_id)
            consumed_banks.add(bank.record_id)
        elif reason == "AMBIGUOUS_CANDIDATES":
            pass  # do not consume — human must pick
        elif reason == "MISSING_COUNTERPART":
            consumed_hit = any("ALREADY_CONSUMED" in c.blockers for c in inv_cands + bank_cands)
            if consumed_hit:
                reason = "DUPLICATE_CANDIDATE"
                decision = "escalate"
                evidence["proof"] = proof_payload(
                    decision=decision,
                    reason=reason,
                    confidence=conf,
                    inv=inv,
                    bank=bank,
                    inv_ranked=inv_cands,
                    bank_ranked=bank_cands,
                    is_tie=is_tie,
                )

        decisions.append(
            Decision(
                settlement_id=s.settlement_id,
                invoice_id=inv.record_id if inv else None,
                bank_txn_id=bank.record_id if bank else None,
                match_type=match_type,
                confidence=conf,
                decision=decision,
                reason_code=reason,
                evidence=evidence,
                invoice_candidates=inv_cands,
                bank_candidates=bank_cands,
                amount=s.amount,
                currency=s.currency,
                txn_type=s.txn_type,
            )
        )

    by_sid = {d.settlement_id: d for d in decisions}
    _try_partial_groups(ordered, invoices, by_sid, consumed_invoices)

    return decisions
