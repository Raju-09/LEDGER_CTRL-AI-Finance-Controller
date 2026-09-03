# Architecture

## What this is

A settlement reconciliation controller: settlements, bank lines, and invoices are generated with known hidden labels, corrupted the way ops data actually breaks, then matched by a **deterministic** engine. A policy gate decides AUTO_CLOSE / ESCALATE / UNRESOLVED. An LLM may *explain* review-band cases. It never writes the decision.

## Pipeline

```
Generate clean ledger
        ↓
Corruption engine (6 types + ambiguous twin + optional 1:N partial)
        ↓
SQLite: source tables  ≠  ground_truth table
        ↓
Candidate blocking → exact → fuzzy score
        ↓
Hard blockers (currency, consumed target)
        ↓
Policy gate ── including never_auto_close_on_tie() ──
        ↓
        ├─ AUTO_CLOSE
        ├─ ESCALATE  (optional LLM explanation, recommend-only)
        └─ UNRESOLVED
        ↓
Audit events (queryable)
        ↓
Evaluate vs hidden labels → precision / recall / false-match rate
```

## Why the LLM does not decide

A wrong auto-close is worse than an exception. Language models invent amounts and pick among twins. Matching is evidence scoring with an explicit tie rule (`matcher/policy.py`). The model is invoked only after the gate has already chosen ESCALATE for the `LOW_CONFIDENCE` band, returns JSON that is schema-validated, and is dropped on timeout (`AI_UNAVAILABLE`) without crashing the run.

## Score

```
0.35 * reference + 0.25 * amount + 0.20 * vendor + 0.20 * date
```

Amount similarity treats `invoice − fee − tax ≈ settlement` as explained, not as a mismatch. Thresholds live in `config.py`, tuned on **dev seed=42**, never on the holdout you report.

## Tie-check (the rule panels probe)

If the top two unblocked candidates differ by `tie_delta` (0.05) or less, the record is ESCALATE / AMBIGUOUS even if the top score is 0.99. That is a named function, not `argmax`.

## Differentiator

The dashboard default view is **what the system refused to auto-close**, ranked by rupee value — not a gallery of perfect matches.

## What we cut

N:M optimizer, agent frameworks, K8s, auth, training, ADRs, drift simulators. Partial payments are 1 invoice → 2 settlements only.
