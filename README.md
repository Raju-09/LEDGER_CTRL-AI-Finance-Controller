# ◇ LEDGER/CTRL - Evidence-First Settlement Reconciliation Controller

<div align="center">

**Global Innovation Hackathon 2026 — Build for a Better Future**  
**Track: FinTech + AI/ML + Generative AI + Data Science (Organized by Bharat Academix)**

[![CI Status](https://img.shields.io/badge/Tests-26%2F26%20Passing-brightgreen?style=flat-square)](tests/)
[![Live Demo](https://img.shields.io/badge/Live%20Demo-Render-46E3B7?style=flat-square&logo=render)](https://ledger-ctrl.onrender.com)
[![Architecture](https://img.shields.io/badge/Architecture-Deterministic%20Waterfall%20%2B%20Policy%20Gate-blue?style=flat-square)](docs/architecture.md)
[![Holdout Freeze](https://img.shields.io/badge/Holdout%20Freeze-Verified%20SHA--256-blueviolet?style=flat-square)](evaluation/freeze/RUN-42-H-92-2AEA.json)
[![Precision](https://img.shields.io/badge/Holdout%20Precision-100.0%25%20(172%2F172)-success?style=flat-square)](#measured-accuracy--holdout-benchmarks)
[![FMR](https://img.shields.io/badge/False%20Match%20Rate-0.0%25%20(0%2F172)-success?style=flat-square)](#measured-accuracy--holdout-benchmarks)
[![Python](https://img.shields.io/badge/Python-3.11%20%7C%203.12%20%7C%203.13-informational?style=flat-square)](https://www.python.org/)
[![License](https://img.shields.io/badge/License-MIT-gray?style=flat-square)](LICENSE)

### *“Close what you can prove. Escalate what you can't.”*

[🚀 Live Cloud Demo](https://ledger-ctrl.onrender.com) · [Local Console](http://127.0.0.1:8000/app) · [Interactive Architecture Flow](#system-architecture) · [5-Minute Video Pitch Script](#5-minute-video-pitch-directors-script) · [Audit & Replay](#deterministic-decision-replay)

</div>

---

## 🎯 Executive Summary & The Problem

Financial reconciliation across settlements, bank statements, and vendor invoices does not fail because data is missing. **It fails because real-world records disagree.**

In production payment rails, transactions arrive corrupted with:
* **Fee deductions & GST withholding** (Settlement ₹97,640 vs Invoice ₹1,00,000)
* **Vendor entity drift** (`"Razorpay Software Pvt Ltd"` vs `"RAZORPAY SOFTWARE"`)
* **Settlement bank latency** ($\pm 1$ to $3$ days date shift)
* **Decoy twins & duplicates** (Identical amounts and vendors with differing invoice IDs)
* **2-Leg partial settlements** (1 invoice reconciled across 2 installment transfers)

### The Failure of Naive "AI Reconcilers"
Most LLM-based reconciliation tools feed raw data into an LLM prompt and ask it to guess matches. In fintech, **this is catastrophic**:
1. **Non-deterministic hallucination:** LLMs invent numbers or flip decisions across identical runs.
2. **Greedy argmax failure:** When presented with two candidates scoring 0.94 and 0.93, probabilistic models guess one. An incorrect auto-close creates irreversible ledger reconciliation debt and misallocated merchant payouts.
3. **Unbounded authority:** Giving an LLM direct database write access violates basic financial auditability.

### The LEDGER/CTRL Solution
**LEDGER/CTRL** is an evidence-first financial control plane. It operates on a strict separation of authority:
* **The Deterministic Policy Engine Decides:** Multi-attribute scoring + invariant policy gating with hard refusal margins ($\Delta \le 0.05$).
* **The Decoupled LLM Only Explains:** The model translates high-dimensional structured evidence into natural language for human investigators. **The LLM cannot authorize, modify, or mutate any financial decision.**

---

## 🏛️ System Architecture

```text
                                  LEDGER/CTRL ARCHITECTURE
                                  
  ┌────────────────────────┐      ┌────────────────────────┐      ┌────────────────────────┐
  │   SETTLEMENT RECORDS   │      │    BANK STATEMENTS     │      │    VENDOR INVOICES     │
  │ (Net, Fee, Tax, UTR)   │      │ (Date, Narration, UTR) │      │ (Gross, Due Date, Tax) │
  └───────────┬────────────┘      └───────────┬────────────┘      └───────────┬────────────┘
              │                               │                               │
              └───────────────────────┬───────┴───────────────────────────────┘
                                      ▼
                        ┌───────────────────────────┐
                        │   INVERTED BLOCKING INDEX │  ← Reduces comparisons by 97.55%
                        │    Candidate Pool K = 12  │    O(N·K) complexity vs O(N²)
                        └─────────────┬─────────────┘
                                      ▼
                        ┌───────────────────────────┐
                        │ DETERMINISTIC SCORING     │  ← Configured & Frozen on DEV
                        │ Ref: 0.35  | Amount: 0.25 │    Fee/Tax algebraic explanation
                        │ Vendor: 0.20 | Date: 0.20 │
                        └─────────────┬─────────────┘
                                      ▼
                        ┌───────────────────────────┐
                        │   INVARIANT POLICY GATE   │
                        │  Score ≥ 0.90 & Margin    │
                        │  never_auto_close_on_tie()│
                        └─────────────┬─────────────┘
                                      │
                 ┌────────────────────┼────────────────────┐
                 │ (Passed All)       │ (Tie Margin ≤0.05) │ (Missing Counterpart)
                 ▼                    ▼                    ▼
        ┌─────────────────┐  ┌─────────────────┐  ┌─────────────────┐
        │   AUTO_CLOSE    │  │    ESCALATE     │  │   UNRESOLVED    │
        │ Proof of Closure│  │ Proof of Refusal│  │ No Counterpart  │
        │ Ledger Consumed │  │ Human Review Q  │  │ Investigation   │
        └────────┬────────┘  └────────┬────────┘  └────────┬────────┘
                 │                    │                    │
                 └────────────────────┼────────────────────┘
                                      ▼
                        ┌───────────────────────────┐
                        │ IMMUTABLE AUDIT TRAIL     │  ← Captures Input, Candidates,
                        │   Deterministic Replay    │    Scores, Policy, & Version IDs
                        └─────────────┬─────────────┘
                                      ▼
                        ┌───────────────────────────┐
                        │ DECOUPLED EXPLAINER (LLM) │  ← ASYNCHRONOUS / READ-ONLY
                        │ AI CAN EXPLAIN.           │    AI_UNAVAILABLE fallback
                        │ POLICY DECIDES.           │    Zero decision mutation
                        └───────────────────────────┘
```

---

## 📊 Measured Accuracy & Holdout Benchmarks

All metrics are evaluated against **hidden, isolated ground truth** stored in a separate table. The matcher never has access to ground-truth labels.

### Canonical Holdout Run (`RUN-42-H-92-2AEA`)
* **Environment:** Seed 42, Split: `holdout`, Records: $N = 237$
* **Configuration:** Matcher v1.4.0, Policy v1.2.0 (Parameters locked on `dev`, untouched on `holdout`)

| Metric | Measured Value | Arithmetic Verification | Operational Significance |
|---|:---:|:---:|---|
| **Match Precision** | **100.0%** | $172 / 172$ | Zero false matches. 100% of auto-closed records matched true counterparts. |
| **False Match Rate (FMR)** | **0.0%** | $0 / 172$ | Never misattributes payouts to incorrect vendors or invoices. |
| **Match Recall** | **89.6%** | $172 / 192$ | Safely recovers 172 true matchable pairs; remaining 20 refused due to policy safety. |
| **Auto-Resolution Rate** | **72.6%** | $172 / 237$ | 172 records auto-closed; 65 escalated/unresolved for human investigation. |
| **Exception Value at Risk** | **₹4.82L** | $\sum 	ext{Amount}_{	ext{Escalated}}$ | Explicitly grouped by reason code: Ambiguity, Amount Drift, Duplicates. |
| **Candidate Blocking Reduction** | **97.55%** | $14,112 	ext{ vs } 576,828$ | At $N=588$, evaluates 14k candidate pairs instead of 576k naive combinations. |
| **Deterministic Throughput** | **~120 rec/s** | Single-threaded | Stateless Python execution. Decoupled from LLM API latency. |

### Multi-Seed Stability Benchmark (4 Independent Seeds)
To prove accuracy is not cherry-picked from a single favorable seed, the identical frozen pipeline was evaluated across 4 independent random seeds ($N pprox 235$ records each):

| Seed | Records ($N$) | Auto-Closed | Escalated | Precision | Recall | Auto-Close FMR | Auto-Rate | Throughput |
|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|
| **42** | 237 | 172 | 65 | **100.0%** | 89.6% | **0.0%** | 72.6% | 118 rec/s |
| **847** | 238 | 179 | 59 | **100.0%** | 90.0% | **0.0%** | 75.2% | 124 rec/s |
| **1204** | 229 | 181 | 48 | **100.0%** | 93.3% | **0.0%** | 79.0% | 115 rec/s |
| **3391** | 233 | 174 | 59 | **100.0%** | 90.6% | **0.0%** | 74.7% | 121 rec/s |
| **MEAN** | **234** | **177** | **58** | **100.0%** | **90.9%** | **0.0%** | **75.4%** | **120 rec/s** |

> **Key Takeaway:** Precision remains rock-solid at **100.0%** across all seeds while recall fluctuates naturally ($89.6\%	ext{--}93.3\%$) with corruption variance. In finance, **precision is non-negotiable; recall is negotiable.**

---

## 🛡️ The Signature Demo: Proof of Refusal

The primary competitive differentiator of LEDGER/CTRL is its refusal behavior under ambiguity.

```text
           THE AMBIGUOUS TWIN DILEMMA
           
SETTLEMENT S-92-0042: ₹50,000 to Acme Traders
   ├── CANDIDATE A (INV-7832): Score = 0.941
   └── CANDIDATE B (INV-7811): Score = 0.932
   
   Score Difference (Δ): 0.009
   Required Policy Tie Margin: 0.050
   
   Greedy Argmax: Auto-closes on Candidate A (HIGH RISK)
   LEDGER/CTRL:   REFUSES AUTO-CLOSE → ESCALATE (AMBIGUOUS_CANDIDATES)
```

In the Evidence Drawer, the operator sees:
```text
┌────────────────────────────────────────────────────────────────────────┐
│ PROOF OF REFUSAL — AMBIGUOUS_CANDIDATES                                │
├────────────────────────────────────────────────────────────────────────┤
│ Candidate A (INV-7832) : Score 0.941                                   │
│ Candidate B (INV-7811) : Score 0.932                                   │
│ Margin Margin          : Δ 0.009 (Required > 0.050)                    │
│                                                                        │
│ POLICY GATE CHECKLIST:                                                 │
│   ✔ Score ≥ 0.900           (0.941)                                    │
│   ✖ Tie Margin > 0.050      (0.009 — FAILED)                           │
│   ✔ Invoice Counterpart     (Present)                                  │
│   ✔ Bank Counterpart        (Present)                                  │
│                                                                        │
│ FINAL VERDICT: ESCALATE                                                │
│ DECISION SOURCE    : DETERMINISTIC POLICY ✔                            │
│ EXPLANATION SOURCE : LLM (DECOUPLED)                                   │
│                                                                        │
│ [AI CAN EXPLAIN · AI CANNOT CHANGE THIS DECISION]                      │
└────────────────────────────────────────────────────────────────────────┘
```

---

## 🧪 Adversarial Safety Lab (Fail-Closed Guarantees)

The built-in Safety Lab executes 5 constructed edge-case fixtures verifying refusal guarantees:

| Test Scenario | Injected Condition | Expected Action | Actual System Result | Invariant Check |
|---|---|---|---|:---:|
| **Ambiguous Twin** | Two decoy invoices with identical amounts & vendors | Block Auto-Close | `ESCALATE (AMBIGUOUS)` | **PASS ✔** |
| **Duplicate Settlement** | Exact duplicate settlement leg | Prevent Double-Consumption | `ESCALATE (DUPLICATE)` | **PASS ✔** |
| **Currency Mismatch** | `INR` settlement vs `USD` invoice | Block Cross-Currency Close | `ESCALATE (CURRENCY_MISMATCH)` | **PASS ✔** |
| **Unexplained Drift** | Amount drift exceeds fee/tax tolerance | Flag Amount Variance | `ESCALATE (AMOUNT_VARIANCE)` | **PASS ✔** |
| **LLM Outage / AI OFF** | OpenAI API timeout / 500 error / disabled | Retain Decision Unchanged | `DECISION IDENTICAL (AI_UNAVAILABLE)` | **PASS ✔** |

---

## 🔒 Security Scope & Operational Bounds

> [!IMPORTANT]
> **Hackathon Prototype Scope:**  
> This implementation is purpose-built as a sandboxed financial control plane evaluating synthetic batches. It does not connect to live payment gateway / banking rails, process merchant PII, or write to production general ledgers.  
> 
> **Production Deployment Requirements:**
> A production rollout would mandate:
> 1. Multi-tenant RBAC and OAuth2 / mTLS authentication.
> 2. Envelope encryption for stored bank credentials (KMS / HashiCorp Vault).
> 3. An append-only distributed event bus (Kafka / AWS Kinesis) for high-throughput audit emission.
> 4. Double-entry accounting bridge connectors with idempotency keys.

---

## 👥 Target Users & Universal Applicability

* **Primary: Finance Operations Analysts** — Process daily settlement batches across payment gateways, banking channels, and ERP invoices without manual spreadsheet triage.
* **Secondary: Finance Controllers & CFO Offices** — Require mathematically proven, auditable reconciliation with zero tolerance for false auto-matches prior to books close.
* **Tertiary: FinTech Platforms & Payment Aggregators** — Scale merchant settlement reconciliation with deterministic precision and automated exception routing.
* **Universal Context ("Innovate Without Borders"):** Settlement friction is jurisdiction-agnostic. Whether reconciling UPI in India, SEPA in Europe, ACH in North America, or M-Pesa in Africa, the evidence-first policy gate operates with zero geographic bias.

---

## 🗺️ Strategic Roadmap & Future Scope

```text
┌──────────────────────────────────────────────────────────────────────────────────┐
│ PHASE 1 (Current): Deterministic Decision Engine & Holdout Evaluation Harness    │
│  ✔ 100% Precision Gate  ✔ Decision Proof Artifacts  ✔ Decoupled LLM Explainer    │
├──────────────────────────────────────────────────────────────────────────────────┤
│ PHASE 2 (Connectors): Live Gateway & ERP Integration                             │
│  ○ Webhook connectors (Razorpay, Stripe)  ○ ERP Sync (SAP, NetSuite)             │
├──────────────────────────────────────────────────────────────────────────────────┤
│ PHASE 3 (Enterprise): Governance, Security & Multi-Tenancy                       │
│  ○ RBAC & mTLS Authentication  ○ KMS Field Encryption  ○ PCI-DSS Audit Controls │
├──────────────────────────────────────────────────────────────────────────────────┤
│ PHASE 4 (Expansion): Full-Suite Finance Operations Control Layer                 │
│  ○ Receivables reconciliation  ○ Dispute queues  ○ Automated Month-End Close     │
├──────────────────────────────────────────────────────────────────────────────────┤
│ PHASE 5 (Global): Cross-Border Multi-Currency Settlement Controller              │
│  ○ Real-time FX tolerance windows  ○ SWIFT / ISO 20022 message parsers           │
└──────────────────────────────────────────────────────────────────────────────────┘
```

---

## 🎬 5-Minute Video Pitch (Director's Script)

Follow this battle-tested script to record your 5-minute submission video:

* **0:00–0:25 [The Thesis]:**  
  *"Financial reconciliation isn't difficult because records don't exist. It's difficult because records disagree—due to fee deductions, UTR truncation, date shifts, and decoy twins. Most AI reconciliation tools fail because they use LLMs to guess matches. In finance, guessing is catastrophic. LEDGER/CTRL is built on one governing principle: **Close what you can prove. Escalate what you can't.**"*
* **0:25–1:15 [The Live Run & Canonical ID]:**  
  *Open `/app`. Seed: 42, Split: Holdout, N: 200.* Click **GENERATE & RECONCILE**.  
  *"In 1.8 seconds, the engine processes 237 records. Look at the canonical run card: Run `RUN-42-H-92-2AEA`. 172 records were safely auto-closed. 65 were refused. ₹4.82L is isolated as exception value at risk. Crucially, every single screen in this system reads from this identical, immutable run object."*
* **1:15–2:15 [The Climax: Proof of Refusal]:**  
  *Go to Exceptions tab, filter `AMBIGUOUS_CANDIDATES`, click Settlement `S-92-0042`.*  
  *"Here is Settlement `S-92-0042`. Two invoices compete: Candidate A scores 0.941, Candidate B scores 0.932. Their difference is 0.009. A greedy argmax matcher would have auto-closed on Candidate A—misallocating funds. Look at our Policy Gate: `Tie margin > 0.05` has failed. The system blocks auto-close and issues `PROOF OF REFUSAL`. Notice the explicit badge: **AI CAN EXPLAIN · AI CANNOT CHANGE THIS DECISION**."*
* **2:15–3:15 [Holdout Evaluation & Denominators]:**  
  *Go to Evaluation tab.*  
  *"We don't hide behind bare percentages: Precision is 100% because **172 out of 172** auto-closes matched hidden ground truth. Recall is 89.6% because **172 out of 192** true matchable pairs were recovered; the rest were safely escalated. Below, our multi-seed benchmark across 4 independent seeds proves that precision remains rock-solid at 100% while recall moves predictably with corruption variance."*
* **3:15–4:00 [AI-OFF & Decision Replay]:**  
  *Toggle LLM Explanation OFF. Switch to Audit tab and click REPLAY DECISION.*  
  *"What happens if OpenAI goes down? I turn AI Explanations OFF. Notice: financial decisions and reason codes remain 100% identical. In the Audit tab, I click **REPLAY DECISION**. Matcher v1.4.0 and policy v1.2.0 re-run against the raw event snapshot. The replay passes with 0 divergences."*
* **4:00–4:45 [Adversarial Safety Lab]:**  
  *Scroll to Safety Lab table in Evaluation tab.*  
  *"Our Safety Lab verifies 5 fail-closed fixtures: duplicates are blocked, twins are refused, and currency mismatches fail closed. The system never guesses."*
* **4:45–5:00 [The Close]:**  
  *"We didn't build an AI chatbot. We built a defensible financial control plane with mathematical bounds, explicit refusal logic, and immutable auditability. In finance, a wrong automatic close is worse than a manual exception. **Close what you can prove. Escalate what you can't.** Thank you."*

---

## ⚡ Quick Start & Verification

### Prerequisites
* Python 3.11+
* SQLite 3

### Installation

```bash
# 1. Clone repository
git clone https://github.com/Raju-09/LEDGER_CTRL-AI-Finance-Controller.git
cd LEDGER_CTRL-AI-Finance-Controller

# 2. Set up virtual environment
python -m venv .venv
# On Windows:
.venv\Scripts\activate
# On Linux/macOS:
source .venv/bin/activate

# 3. Install dependencies
pip install -r requirements.txt

# 4. Optional: Configure OpenAI API Key for natural-language explanations
cp .env.example .env
# Edit .env and set OPENAI_API_KEY=your_key (Optional: system runs 100% standalone without it)
```

### Run Test Suite (26 Automated Tests)

```bash
python -m pytest tests/ -v
```

Output:
```text
tests/integration/test_api.py::test_generate_and_reconcile PASSED        [  3%]
tests/unit/test_corruption_cases.py (9 tests) PASSED                     [ 38%]
tests/unit/test_p1_features.py (3 tests) PASSED                          [ 50%]
tests/unit/test_trust_controls.py (13 tests) PASSED                      [100%]
============================== 26 passed in 8.52s ==============================
```

### Start Local Web Console

```bash
uvicorn api.main:app --host 127.0.0.1 --port 8000 --reload
```

* **Interactive Landing Overview:** [http://127.0.0.1:8000](http://127.0.0.1:8000)
* **Reconciliation Operator Console:** [http://127.0.0.1:8000/app](http://127.0.0.1:8000/app)

---

## 📂 Repository File Tree

```text
LEDGER_CTRL-AI-Finance-Controller/
├── api/
│   ├── main.py              # FastAPI endpoints & static asset mounts
│   ├── pipeline.py          # 6-stage reconciliation execution pipeline
│   └── benchmark.py         # Multi-seed & throughput scaling harnesses
├── matcher/
│   ├── engine.py            # Deterministic matching waterfall (exact → fuzzy)
│   ├── policy.py            # Policy gate & never_auto_close_on_tie() logic
│   ├── scoring.py           # Multi-attribute similarity scoring (weights locked on DEV)
│   ├── normalize.py         # Vendor name, UTR, and date normalization
│   └── money.py             # Decimal minor-unit financial arithmetic
├── generator/
│   └── engine.py            # Synthetic batch generator (8 real-world corruptions)
├── evaluation/
│   ├── metrics.py           # Confusion matrix & holdout evaluation logic
│   ├── safety_lab.py        # 5 constructed fail-closed safety fixtures
│   └── freeze/
│       └── RUN-42-H-92-2AEA.json # Cryptographic holdout freeze artifact
├── llm/
│   └── explainer.py         # Decoupled, asynchronous natural language explainer
├── db/
│   ├── schema.py            # SQLAlchemy database tables & audit models
│   └── store.py             # SQLite persistence & immutable audit log store
├── frontend/
│   ├── landing.html         # Editorial landing overview
│   ├── app.html             # Operational reconciliation console
│   ├── app.js               # Reactive client state & drawer rendering
│   ├── design.css           # High-density fintech design system
│   └── favicon.svg          # Geometric vector logo mark
├── tests/
│   ├── integration/         # Full batch API integration tests
│   └── unit/                # Corruption, trust controls, and invariant unit tests
├── docs/
│   ├── architecture.md      # Detailed system architecture specification
│   └── failures.md          # Real engineering failure log & resolutions
├── requirements.txt         # Pinned Python dependencies
└── README.md                # System specification & submission document
```

---

<div align="center">

**Global Innovation Hackathon 2026 — Build for a Better Future**  
*Track: FinTech + AI/ML + Generative AI + Data Science*  
*Organized by Bharat Academix · Developed by Raju Sammeta*

</div>

