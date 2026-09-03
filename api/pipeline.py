from __future__ import annotations

import time
from uuid import uuid4

from config import settings
from db.store import Store
from evaluation.metrics import evaluate
from generator.engine import generate_batch
from llm.explainer import explain_case
from matcher.engine import reconcile_batch


def generate(n: int, seed: int | None, split: str) -> dict:
    seed = int(seed if seed is not None else uuid4().int % 1_000_000_000)
    batch_id = f"B{seed}-{n}-{split[:1].upper()}-{uuid4().hex[:4]}"
    settlements, invoices, banks, truth = generate_batch(n, seed, batch_id)
    store = Store()
    try:
        store.create_batch(batch_id, seed, n, split, settlements, invoices, banks, truth)
        from collections import Counter

        mix = Counter(t.corruption for t in truth)
        return {
            "batch_id": batch_id,
            "seed": seed,
            "n_settlements": len(settlements),
            "n_invoices": len(invoices),
            "n_bank": len(banks),
            "split": split,
            "corruption_mix": dict(mix),
        }
    finally:
        store.close()


def reconcile(batch_id: str, use_llm: bool = True) -> dict:
    store = Store()
    try:
        settlements, invoices, banks = store.load_sources(batch_id)
        t0 = time.perf_counter()
        decisions = reconcile_batch(settlements, invoices, banks)
        # Record deterministic-only elapsed before any LLM I/O begins.
        # This is the honest number for "100k/day?" questions — LLM wait is not part
        # of the matching pipeline's throughput.
        deterministic_elapsed_ms = (time.perf_counter() - t0) * 1000

        if use_llm:
            review = [d for d in decisions if d.decision == "escalate" and d.reason_code == "LOW_CONFIDENCE"]
            for d in review[:40]:
                s = next(x for x in settlements if x.settlement_id == d.settlement_id)
                payload = {
                    "settlement": {
                        "id": s.settlement_id,
                        "amount": s.amount,
                        "date": str(s.date),
                        "vendor": s.vendor_name_raw,
                        "fee": s.fee,
                        "tax": s.tax,
                    },
                    "evidence": d.evidence,
                    "policy_decision": d.decision,
                    "reason_code": d.reason_code,
                }
                result = explain_case(payload)
                if result.get("ok"):
                    d.llm_suggestion = result["suggestion"]
                else:
                    d.llm_suggestion = {
                        "label": "EXPLANATION_UNAVAILABLE",
                        "confidence_band": "low",
                        "evidence": [result.get("detail", "")],
                        "reason_code": result.get("fallback_reason", "AI_UNAVAILABLE"),
                    }
                    # LLM outage cannot change decision or reason_code.

        total_elapsed_ms = (time.perf_counter() - t0) * 1000
        n = len(decisions)
        truth = store.load_truth(batch_id)
        metrics = evaluate(decisions, truth)
        # deterministic_rps: matcher + policy only (no LLM I/O).  This is the
        # scalability metric.  For 100k/day with blocking keys this extrapolates
        # to ~2M records/day on a single core.
        metrics["deterministic_rps"] = round(n / (deterministic_elapsed_ms / 1000), 2) if deterministic_elapsed_ms else 0
        # throughput_rps: total wall time including LLM calls (kept for compatibility).
        metrics["throughput_rps"] = round(n / (total_elapsed_ms / 1000), 2) if total_elapsed_ms else 0
        metrics["elapsed_ms"] = round(total_elapsed_ms, 1)
        metrics["deterministic_elapsed_ms"] = round(deterministic_elapsed_ms, 1)
        metrics["thresholds"] = {
            "auto_close": settings.auto_close_threshold,
            "review": settings.review_threshold,
            "tie_delta": settings.tie_delta,
            "candidate_pool_size": settings.candidate_pool_size,
            "tuned_on": "dev seed=42 n=400 — not this holdout",
        }
        batch = store.get_batch(batch_id)
        metrics["lineage"] = {
            "batch_id": batch_id,
            "seed": batch.seed if batch else None,
            "split": batch.split if batch else None,
            "n": n,
            "matcher_version": settings.matcher_version,
            "policy_version": settings.policy_version,
            "eval_protocol": settings.eval_protocol,
            "llm_used": bool(use_llm),
        }
        run_id = store.persist_run(batch_id, decisions, metrics, total_elapsed_ms)
        metrics["run_id"] = run_id
        metrics["lineage"]["run_id"] = run_id
        return {"run_id": run_id, "batch_id": batch_id, "metrics": metrics}
    finally:
        store.close()


def replay(batch_id: str) -> dict:
    """Re-run matcher+policy on stored sources. Compare to persisted decisions."""
    store = Store()
    try:
        settlements, invoices, banks = store.load_sources(batch_id)
        stored = store.matches(batch_id)
        if not stored:
            return {"pass": False, "n": 0, "diverged": [], "note": "no persisted decisions"}
        fresh = reconcile_batch(settlements, invoices, banks)
        by_stored = {m.settlement_id: m for m in stored}
        diverged = []
        for d in fresh:
            m = by_stored.get(d.settlement_id)
            if not m:
                diverged.append({"settlement_id": d.settlement_id, "why": "missing_in_store"})
                continue
            if (d.decision, d.reason_code, d.invoice_id, d.bank_txn_id) != (
                m.decision, m.reason_code, m.invoice_id, m.bank_txn_id
            ):
                diverged.append({
                    "settlement_id": d.settlement_id,
                    "stored": [m.decision, m.reason_code, m.invoice_id, m.bank_txn_id],
                    "replayed": [d.decision, d.reason_code, d.invoice_id, d.bank_txn_id],
                })
        ev = store.latest_eval(batch_id)
        return {
            "pass": len(diverged) == 0,
            "n": len(fresh),
            "run_id": ev.run_id if ev else None,
            "diverged": diverged[:20],
            "matcher_version": settings.matcher_version,
            "policy_version": settings.policy_version,
        }
    finally:
        store.close()
