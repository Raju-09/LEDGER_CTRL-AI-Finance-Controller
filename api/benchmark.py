"""Benchmark: multi-seed evaluation and throughput scaling."""
from __future__ import annotations
import time
from uuid import uuid4

from config import settings
from evaluation.metrics import evaluate
from generator.engine import generate_batch
from matcher.engine import reconcile_batch


def run_seeds(seeds: list[int], n: int) -> list[dict]:
    results = []
    for seed in seeds:
        bid = f"BENCH-{seed}-{n}-{uuid4().hex[:4]}"
        settlements, invoices, banks, truth = generate_batch(n, seed, bid)
        t0 = time.perf_counter()
        decisions = reconcile_batch(settlements, invoices, banks)
        elapsed_ms = (time.perf_counter() - t0) * 1000
        metrics = evaluate(decisions, truth)
        n_dec = len(decisions)
        results.append({
            "seed": seed,
            "n": n_dec,
            "auto_closed": metrics["auto_matched"],
            "escalated": metrics["escalated"],
            "unresolved": metrics["unresolved"],
            "precision": round(metrics["precision"], 4),
            "recall": round(metrics["recall"], 4),
            "fmr": round(metrics["false_match_rate"], 4),
            "auto_rate": round(metrics["auto_resolution_rate"], 4),
            "exception_value": metrics["exception_value"],
            "confusion": metrics.get("confusion"),
            "split": "holdout",
            "matcher_version": settings.matcher_version,
            "policy_version": settings.policy_version,
            "elapsed_ms": round(elapsed_ms, 1),
            "rps": round(n_dec / (elapsed_ms / 1000), 0) if elapsed_ms else 0,
        })
    if results:
        keys = ["precision", "recall", "fmr", "auto_rate", "rps", "auto_closed", "escalated"]
        mean = {k: round(sum(r[k] for r in results) / len(results), 4) for k in keys}
        mean["seed"] = "MEAN"
        mean["n"] = round(sum(r["n"] for r in results) / len(results), 1)
        mean["elapsed_ms"] = None
        mean["note"] = "Stability across independently generated synthetic batches — not production generalization."
        results.append(mean)
    return results

def run_throughput(sizes: list[int], seed: int = 42) -> list[dict]:
    results = []
    for n in sizes:
        bid = f"BENCH-TP-{n}-{uuid4().hex[:4]}"
        settlements, invoices, banks, truth = generate_batch(n, seed, bid)
        n_s = len(settlements); n_i = len(invoices); n_b = len(banks)
        naive = n_s * (n_i + n_b)
        t0 = time.perf_counter()
        decisions = reconcile_batch(settlements, invoices, banks)
        elapsed = time.perf_counter() - t0
        total_cands = sum(
            len(d.invoice_candidates) + len(d.bank_candidates) for d in decisions
        )
        reduction = round(1 - total_cands / max(naive, 1), 4)
        results.append({
            "n":                  len(decisions),
            "elapsed_s":          round(elapsed, 3),
            "rps":                round(len(decisions) / elapsed, 0) if elapsed else 0,
            "total_candidates":   total_cands,
            "naive_comparisons":  naive,
            "blocking_reduction": reduction,
        })
    return results
