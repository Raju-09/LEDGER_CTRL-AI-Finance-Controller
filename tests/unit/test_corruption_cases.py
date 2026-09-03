"""Corruption-case tests: the matcher never receives ground-truth rows."""

from matcher.engine import reconcile_batch
from matcher.policy import never_auto_close_on_tie
from models import CandidateScore
from generator.engine import generate_batch, corruption_counts
from evaluation.metrics import evaluate


def _run(n=80, seed=7, include_partial=True):
    s, i, b, t = generate_batch(n, seed, "TESTBAT", include_partial=include_partial)
    d = reconcile_batch(s, i, b)
    return s, i, b, t, d


def test_generator_covers_six_types():
    _, _, _, truth = generate_batch(120, 11, "MIX", include_partial=False)
    counts = corruption_counts(truth)
    for k in ("exact", "date_shift", "amount_delta", "vendor_variation", "duplicate", "orphan"):
        assert counts.get(k, 0) >= 1, counts
    assert counts.get("ambiguous_twin", 0) >= 1


def test_labels_are_separate():
    settlements, _, _, truth = generate_batch(40, 3, "SEP")
    ids = {s.settlement_id for s in settlements}
    assert {t.settlement_id for t in truth} <= ids
    assert not any(hasattr(s, "true_invoice_id") for s in settlements)


def test_tie_check_is_explicit():
    a = CandidateScore("I1", 0.94, "fuzzy", {}, [])
    b = CandidateScore("I2", 0.93, "fuzzy", {}, [])
    assert never_auto_close_on_tie([a, b]) is True
    c = CandidateScore("I3", 0.80, "fuzzy", {}, [])
    assert never_auto_close_on_tie([a, c]) is False
    assert never_auto_close_on_tie([a]) is False


def test_ambiguous_twin_never_auto_close():
    _, _, _, truth, decisions = _run(100, 21)
    by = {d.settlement_id: d for d in decisions}
    twins = [t for t in truth if t.corruption == "ambiguous_twin"]
    assert twins
    for t in twins:
        assert by[t.settlement_id].decision != "auto_close"
        assert by[t.settlement_id].reason_code in {"AMBIGUOUS", "AMBIGUOUS_CANDIDATES"}


def test_orphan_not_forced():
    _, _, _, truth, decisions = _run(90, 5)
    by = {d.settlement_id: d for d in decisions}
    orphans = [t for t in truth if t.corruption == "orphan"]
    assert orphans
    for t in orphans:
        assert by[t.settlement_id].decision != "auto_close"


def test_duplicate_does_not_double_consume():
    _, _, _, truth, decisions = _run(80, 9)
    dups = [t for t in truth if t.corruption == "duplicate"]
    assert dups
    one_to_one = [
        d.invoice_id
        for d in decisions
        if d.decision == "auto_close" and d.invoice_id and d.reason_code != "PARTIAL_PAYMENT"
    ]
    assert len(one_to_one) == len(set(one_to_one))
    by = {d.settlement_id: d for d in decisions}
    for t in dups:
        assert by[t.settlement_id].decision != "auto_close"


def test_date_shift_often_matches():
    _, _, _, truth, decisions = _run(100, 42)
    by = {d.settlement_id: d for d in decisions}
    shifted = [t for t in truth if t.corruption == "date_shift"]
    ok = sum(
        1
        for t in shifted
        if by[t.settlement_id].decision == "auto_close"
        and by[t.settlement_id].invoice_id == t.invoice_id
        and by[t.settlement_id].bank_txn_id == t.bank_txn_id
    )
    assert shifted
    assert ok / len(shifted) >= 0.4


def test_amount_delta_fee_explained():
    _, _, _, truth, decisions = _run(80, 17)
    by = {d.settlement_id: d for d in decisions}
    deltas = [t for t in truth if t.corruption == "amount_delta"]
    assert deltas
    explained = [
        by[t.settlement_id]
        for t in deltas
        if by[t.settlement_id].evidence.get("fee_explained_invoice")
        or by[t.settlement_id].decision == "auto_close"
    ]
    assert explained


def test_holdout_metrics_honest():
    _, _, _, truth, decisions = _run(120, 99)
    m = evaluate(decisions, truth)
    assert 0 <= m["precision"] <= 1
    assert 0 <= m["recall"] <= 1
    assert m["records_processed"] == len(decisions)
    assert "false_match_rate" in m
    # recall is auto-closes of true pairs, so it should not be 1.0 once twins/orphans exist
    assert m["exception_rate"] > 0
