# ◇ LEDGER/CTRL — Evidence-first settlement reconciliation controller

> **Razorpay AI Buildathon Submission — Finance Controller Track**  
> *Close what you can prove. Escalate what you can't.*

> [!IMPORTANT]
> **Safety Boundary:** LEDGER/CTRL does not allow the LLM to determine or authorize reconciliation decisions. Financial decisions are produced entirely by the deterministic matching engine and policy gate. The LLM is used only for evidence-grounded explanations of decisions already made by the policy layer.

---

## Measured Accuracy & Multi-Seed Benchmarks

| Metric | Measured Value | Operational Meaning |
|---|---|---|
| **Precision (Holdout, seed 42)** | **100.0%** | On this freeze: $172 / 172$ auto-closes matched hidden counterparts. |
| **False Match Rate (FMR)** | **0.0%** | $0 / 172$ wrong auto-closes. |
| **Recall (Holdout, seed 42)** | **89.6%** | $172 / 192$ true matchable pairs auto-closed; the rest were refused. |
| **Auto-Resolution Rate** | **72.6%** | $172 / 237$ records auto-closed; $65$ escalated. |
| **Candidate Blocking Reduction** | **97.55%** at $N=588$ | $14,112$ candidate evaluations vs $576,828$ naive $O(N^2)$ pairs. |
| **Deterministic Throughput** | **~70–120 rec/s** | Matcher + policy only (LLM explanation is decoupled). |
| **Automated Tests** | **26/26 Passing** | Unit + integration covering GT isolation, money, safety lab, replay, AI OFF. |

### Multi-Seed Stability Benchmark (4 independent seeds)

Evaluated across 4 independent seeds ($N \approx 235$ records). This is **synthetic-batch stability**, not a production-generalization claim:

```text
Seed    N     Auto-Closed  Escalated  Precision  Recall   Auto-Close FMR  Auto-Rate
42     237       172          65       100.0%    89.6%        0.0%         72.6%
847    238       179          59       100.0%    90.0%        0.0%         75.2%
1204   229       181          48       100.0%    93.3%        0.0%         79.0%
3391   233       174          59       100.0%    90.6%        0.0%         74.7%
-----------------------------------------------------------------------------------
MEAN   234       177          58       100.0%    90.9%        0.0%         75.4%
```

On this freeze, precision stayed 100% while recall moved with the corruption mix. That is the intended tradeoff: **precision is non-negotiable; recall is negotiable.**

---

## Evaluation Methodology & Ground Truth Isolation

```text
SYNTHETIC GENERATOR
        │
   ┌────┴────────────────────────┐
   ▼                             ▼
OBSERVED RECORDS          HIDDEN GROUND TRUTH
(Settlement, Invoice,     (true_group_id, true_invoice_id,
 Bank Statement)           true_bank_txn_id, corruption_type)
        │                             │
   [Matcher has NO access to truth]   │
        │                             │
   DETERMINISTIC MATCHER              │
        │                             │
   POLICY GATE                        │
        │                             │
   PREDICTED DECISIONS                │
        │                             │
        └──────────────┬──────────────┘
                       ▼
               HOLDOUT EVALUATOR
         (Precision / Recall / FMR)
```

1. **Strict Information Hiding:** The matcher operates solely on observed records (`Settlement`, `Invoice`, `BankStatement`). Source models contain no foreign keys, labels, or ground-truth group IDs.
2. **Hidden Ground Truth:** Stored in a separate table (`ground_truth`) and queried exclusively by `evaluation/metrics.py` after matching finishes.
3. **No Threshold Leakage:** Scoring weights (`ref: 0.35, amt: 0.25, vendor: 0.20, date: 0.20`), auto-close threshold (`0.90`), and tie margin (`0.05`) were fixed on `DEV` split and remained frozen for all `HOLDOUT` evaluations.
4. **Confusion Matrix Semantics:**
   * **True Positive (TP):** True matchable pair predicted as `AUTO_CLOSE` with correct invoice and bank IDs.
   * **False Positive (FP):** `AUTO_CLOSE` on an incorrect counterpart, orphan, or duplicate.
   * **False Negative (FN):** True matchable pair escalated or left unresolved (counted against match recall).
   * **True Negative (TN):** Orphans and corrupt duplicates correctly escalated or refused.

---

## Production-Shaped Synthetic Data & Corruptions

Each batch injects 8 real-world corruption categories:
1. **Exact Matches (~40%):** Clean reference, amount, and date alignment.
2. **Date Shift (~15%):** $\pm 1$ to $3$ days settlement lag between bank and invoice.
3. **Amount Delta / Fee Explanation (~15%):** Settlement amount reflects gross invoice minus platform fee ($1.5\text{--}2.5\%$) and GST ($18\%$).
4. **Vendor Name Variation (~10%):** Legal entity abbreviations (`Pvt Ltd` vs `Private Limited`, punctuation, capitalization shifts).
5. **Duplicate Transactions (~10%):** Exact duplicate settlements; policy guarantees only one can match, duplicate is blocked.
6. **Orphans (~10%):** Settlements missing an invoice, a bank statement, or both.
7. **Ambiguous Twins (~3%):** Identical decoy invoices sharing amount and vendor; policy tie-check triggers hard refusal ($\Delta \le 0.05$).
8. **2-Leg Partial Settlements (~8%):** Single invoice paid across two settlement legs; reconciled only when leg amounts uniquely sum to invoice.

---

## Decision semantics

- **AUTO_CLOSE** — policy-authorized reconciliation closure in this sandbox. Not a general-ledger write.
- **ESCALATE** — at least one candidate exists; evidence is insufficient (tie, amount, currency, duplicate, nearby decoy).
- **UNRESOLVED** — no valid counterpart was established. If an orphan still has a decoy candidate nearby, that is ESCALATE, not UNRESOLVED.

## Policy Gate & Refusal Hierarchy

Automatic closure requires clearing all policy conditions simultaneously:
```text
IF min(score_inv, score_bank) >= 0.90:
    IF abs(cand[0].score - cand[1].score) <= 0.05:
        DECISION = ESCALATE, REASON = AMBIGUOUS (TIE REFUSAL)
    ELSE IF counterpart_missing:
        DECISION = UNRESOLVED, REASON = MISSING_COUNTERPART
    ELSE IF currency_mismatch:
        DECISION = ESCALATE, REASON = CURRENCY_MISMATCH
    ELSE:
        DECISION = AUTO_CLOSE (AUTHORIZED)
ELSE IF min(score_inv, score_bank) >= 0.60:
    DECISION = ESCALATE, REASON = LOW_CONFIDENCE
ELSE:
    DECISION = UNRESOLVED, REASON = NO_CONFIDENT_MATCH
```

---

## Known Limitations

1. **Synthetic sandbox:** Production-shaped batches only. No Razorpay settlement files, no merchant PII, no general-ledger posting.
2. **Demo security scope:** Local SQLite, no auth, CORS `*`. This submission operates on synthetic financial data in a local/demo environment. It does not process merchant PII, does not connect to production Razorpay systems, and does not post to a general ledger. Production deployment would require: authentication, authorization / tenant isolation, secrets management, restricted CORS, encrypted storage, production audit infrastructure, and connector-level access controls. CSV export sanitizes formula prefixes (`= + - @`). Import APIs are not the product; do not demo them.
3. **Partial settlements:** 2-leg only. N-leg subset-sum is `UNSUPPORTED_PARTIAL`.
4. **FX:** Currency must match. Mismatch is refused; no conversion.
5. **LLM:** Explain-only. Outage, timeout, or AI OFF cannot change a decision.
6. **Cash position / Q&A / tax matcher:** Explicit non-goals. One proven recon loop beat two unproven products.

---

## 5-minute demo (run this, not a feature tour)

Open `/app`. LLM **disabled**. Seed **42**, split **holdout**, N **200**.

1. **0:00–0:20** — “Wrong auto-close is worse than a manual exception. Policy decides. AI explains. Cash forecast was refused as a second unproven system.”
2. **0:20–1:10** — Generate & reconcile. Point at the canonical `run_id`, **HOLDOUT**, N, auto-closed / refused, exception rupees.
3. **1:10–2:10** — Filter `ESCALATE` + `AMBIGUOUS_CANDIDATES`. Open the twin. Proof of refusal: two scores, margin ≤ 0.05, **the system could have matched this and didn’t.**
4. **2:10–3:00** — Evaluation: precision **172 / 172** (or that run’s denominator), recall vs true-matchable, FMR **0 / auto-closes**, confusion counts. Same `run_id` as Pipeline.
5. **3:00–3:40** — **AI OFF CHECK** then **REPLAY**. Decisions identical. LLM cannot mutate them.
6. **3:40–4:20** — Safety lab: twins, duplicate, currency, refund, prompt-injection-as-data.
7. **4:20–5:00** — “On holdout seed 42: **172 of 237** auto-closed, **zero wrong closes**. Close what you can prove.”

---

## Quick Start

```bash
# 1. Activate virtual environment
python -m venv .venv
# Windows: .venv\Scripts\activate

# 2. Install dependencies
pip install -r requirements.txt

# 3. Run test suite
python -m pytest tests/ -v

# 4. Run live server
uvicorn api.main:app --host 127.0.0.1 --port 8000 --reload
```

* **Landing Overview:** Open [http://127.0.0.1:8000](http://127.0.0.1:8000)
* **Reconciliation Console:** Open [http://127.0.0.1:8000/app](http://127.0.0.1:8000/app)
