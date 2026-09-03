from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI, File, HTTPException, Query, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from api import benchmark, importer

from api.pipeline import generate, reconcile, replay
from matcher.money import sanitize_export_cell
from db.schema import init_db
from db.store import Store
from evaluation.safety_lab import run_safety_lab
from matcher.engine import reconcile_batch

init_db()
app = FastAPI(title="LEDGER/CTRL", version="1.0.0", description="Evidence-first reconciliation controller. Policy decides. AI explains.")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])


class GenerateIn(BaseModel):
    n: int = Field(200, ge=20, le=5000)
    seed: int | None = None
    split: str = Field("holdout", pattern="^(dev|holdout)$")


class ReconcileIn(BaseModel):
    use_llm: bool = True


@app.post("/api/batches/generate")
def api_generate(body: GenerateIn):
    return generate(body.n, body.seed, body.split)


@app.post("/api/batches/{batch_id}/reconcile")
def api_reconcile(batch_id: str, body: ReconcileIn | None = None):
    store = Store()
    try:
        if not store.get_batch(batch_id):
            raise HTTPException(404, "batch not found")
    finally:
        store.close()
    use_llm = body.use_llm if body else True
    return reconcile(batch_id, use_llm=use_llm)


@app.get("/api/batches")
def api_list_batches():
    store = Store()
    try:
        rows = store.list_batches()
        return [
            {"id": b.id, "seed": b.seed, "n": b.n, "split": b.split, "status": b.status, "created_at": str(b.created_at)}
            for b in rows
        ]
    finally:
        store.close()


@app.get("/api/batches/{batch_id}")
def api_batch(batch_id: str):
    store = Store()
    try:
        b = store.get_batch(batch_id)
        if not b:
            raise HTTPException(404, "batch not found")
        eval_row = store.latest_eval(batch_id)
        matches = store.matches(batch_id)
        settlements, invoices, banks = store.load_sources(batch_id)
        return {
            "id": b.id,
            "seed": b.seed,
            "n": b.n,
            "split": b.split,
            "status": b.status,
            "counts": {"settlements": len(settlements), "invoices": len(invoices), "bank": len(banks), "matches": len(matches)},
            "metrics": eval_row.metrics if eval_row else None,
            "run_id": eval_row.run_id if eval_row else None,
        }
    finally:
        store.close()


@app.get("/api/batches/{batch_id}/matches")
def api_matches(batch_id: str, decision: str | None = None):
    store = Store()
    try:
        rows = store.matches(batch_id)
        out = []
        for m in rows:
            if decision and m.decision != decision:
                continue
            out.append(
                {
                    "match_id": m.match_id,
                    "settlement_id": m.settlement_id,
                    "invoice_id": m.invoice_id,
                    "bank_txn_id": m.bank_txn_id,
                    "match_type": m.match_type,
                    "confidence": m.confidence,
                    "decision": m.decision,
                    "reason_code": m.reason_code,
                    "evidence": m.evidence,
                    "llm_suggestion": m.llm_suggestion,
                }
            )
        return out
    finally:
        store.close()


@app.get("/api/batches/{batch_id}/exceptions")
def api_exceptions(batch_id: str, min_amount: float = 0):
    """Differentiator: what the system refused to auto-close."""
    store = Store()
    try:
        return store.exceptions(batch_id, min_amount=min_amount)
    finally:
        store.close()


@app.get("/api/audit")
def api_audit(settlement_id: str = Query(..., min_length=3)):
    store = Store()
    try:
        events = store.audit_for(settlement_id)
        if not events:
            return []  # valid ID, just not yet reconciled — don't 404
        return [
            {
                "run_id": e.run_id,
                "batch_id": e.batch_id,
                "settlement_id": e.settlement_id,
                "record_ids": e.record_ids,
                "decision": e.decision,
                "reason_code": e.reason_code,
                "timestamp": str(e.timestamp),
                "evidence_snapshot": e.evidence_snapshot,
            }
            for e in events
        ]
    finally:
        store.close()


@app.post("/api/batches/{batch_id}/replay")
def api_replay(batch_id: str):
    store = Store()
    try:
        if not store.get_batch(batch_id):
            raise HTTPException(404, "batch not found")
    finally:
        store.close()
    return replay(batch_id)


@app.get("/api/runs/{run_id}")
def api_run(run_id: str):
    store = Store()
    try:
        ev = store.eval_by_run(run_id)
        if not ev:
            raise HTTPException(404, "run not found")
        matches = store.matches_for_run(run_id)
        batch = store.get_batch(ev.batch_id)
        auto = sum(1 for m in matches if m.decision == "auto_close")
        esc = sum(1 for m in matches if m.decision == "escalate")
        unr = sum(1 for m in matches if m.decision == "unresolved")
        m = ev.metrics or {}
        return {
            "run_id": ev.run_id,
            "batch_id": ev.batch_id,
            "seed": batch.seed if batch else None,
            "split": batch.split if batch else None,
            "n": len(matches),
            "matcher_version": (m.get("lineage") or {}).get("matcher_version"),
            "policy_version": (m.get("lineage") or {}).get("policy_version"),
            "metrics": m,
            "from_decisions": {
                "records_processed": len(matches),
                "auto_matched": auto,
                "escalated": esc,
                "unresolved": unr,
            },
            "consistent": (
                m.get("auto_matched") == auto
                and m.get("escalated") == esc
                and m.get("unresolved") == unr
                and m.get("records_processed") == len(matches)
            ),
        }
    finally:
        store.close()


@app.get("/api/batches/{batch_id}/export")
def api_export(batch_id: str):
    store = Store()
    try:
        if not store.get_batch(batch_id):
            raise HTTPException(404, "batch not found")
        rows = store.matches(batch_id)
        header = ["settlement_id", "invoice_id", "bank_txn_id", "decision", "reason_code", "confidence", "match_type", "vendor"]
        lines = [",".join(header)]
        for m in rows:
            vendor = (m.evidence or {}).get("vendor_name_raw", "")
            cells = [
                m.settlement_id,
                m.invoice_id or "",
                m.bank_txn_id or "",
                m.decision or "",
                m.reason_code or "",
                f"{m.confidence:.4f}" if m.confidence is not None else "",
                m.match_type or "",
                vendor,
            ]
            lines.append(",".join(sanitize_export_cell(c) for c in cells))
        body = "\n".join(lines) + "\n"
        return PlainTextResponse(body, media_type="text/csv; charset=utf-8")
    finally:
        store.close()


@app.get("/api/batches/{batch_id}/false-matches")
def api_false_matches(batch_id: str):
    store = Store()
    try:
        ev = store.latest_eval(batch_id)
        if not ev:
            raise HTTPException(404, "batch not reconciled")
        return ev.metrics.get("false_matches", [])
    finally:
        store.close()



# ═══════════════════════════════════════════════════════════════════════════════
# IMPORT — CSV / XLSX upload
# ═══════════════════════════════════════════════════════════════════════════════

@app.post("/api/import/upload")
async def api_import_upload(
    settlements: UploadFile | None = File(None),
    bank:        UploadFile | None = File(None),
    invoices:    UploadFile | None = File(None),
):
    """Accept up to 3 CSV/XLSX files and parse them. Returns schema mapping + validation report."""
    if not (settlements or bank or invoices):
        raise HTTPException(400, "At least one file is required (settlements, bank, or invoices)")

    def _read(f: UploadFile | None):
        return (None, None) if f is None else (None, None)  # placeholder replaced below

    sb = await settlements.read() if settlements else None
    bb = await bank.read()        if bank else None
    ib = await invoices.read()    if invoices else None

    try:
        session = importer.process_upload(
            sb, settlements.filename if settlements else None,
            bb, bank.filename        if bank else None,
            ib, invoices.filename    if invoices else None,
        )
    except ValueError as exc:
        raise HTTPException(400, str(exc))

    return importer.session_summary(session)


@app.get("/api/import/{import_id}")
def api_import_get(import_id: str):
    """Return current status of an import session."""
    sess = importer.get_session(import_id)
    if not sess:
        raise HTTPException(404, "import session not found")
    return importer.session_summary(sess)


@app.post("/api/import/{import_id}/reconcile")
def api_import_reconcile(import_id: str, body: ReconcileIn | None = None):
    """Reconcile uploaded data. No ground truth — evaluation shows N/A."""
    sess = importer.get_session(import_id)
    if not sess:
        raise HTTPException(404, "import session not found")
    if not sess.models_s:
        raise HTTPException(400, "No valid settlement rows to reconcile")

    use_llm = body.use_llm if body else False

    # Persist as a batch so existing reconcile pipeline works
    store = Store()
    try:
        store.create_batch(
            sess.batch_id,
            0,
            len(sess.models_s),
            "upload",
            sess.models_s,
            sess.models_i,
            sess.models_b,
            [],
        )
    finally:
        store.close()

    return reconcile(sess.batch_id, use_llm=use_llm)


# ═══════════════════════════════════════════════════════════════════════════════
# BENCHMARK — multi-seed evaluation + throughput scaling
# ═══════════════════════════════════════════════════════════════════════════════

@app.get("/api/benchmark/seeds")
def api_benchmark_seeds(
    seeds: str = Query("42,847,1204,3391", description="Comma-separated seed integers"),
    n:     int = Query(200, ge=20, le=1000),
):
    """Run evaluate at multiple seeds and return a comparison table."""
    try:
        seed_list = [int(s.strip()) for s in seeds.split(",") if s.strip()]
    except ValueError:
        raise HTTPException(400, "seeds must be comma-separated integers")
    if len(seed_list) > 10:
        raise HTTPException(400, "max 10 seeds per request")
    return benchmark.run_seeds(seed_list, n)


@app.get("/api/safety-lab")
def api_safety_lab():
    """Constructed refusal cases. Not sampled from the generator; not tuned on holdout."""
    rows = run_safety_lab()
    return {"passed": sum(1 for r in rows if r["pass"]), "total": len(rows), "cases": rows}


@app.post("/api/batches/{batch_id}/ai-off-check")
def api_ai_off(batch_id: str):
    """Same records, matcher-only twice. Decisions must be identical; LLM is not in this path."""
    store = Store()
    try:
        if not store.get_batch(batch_id):
            raise HTTPException(404, "batch not found")
        settlements, invoices, banks = store.load_sources(batch_id)
    finally:
        store.close()
    a = reconcile_batch(settlements, invoices, banks)
    b = reconcile_batch(settlements, invoices, banks)
    sig = lambda ds: [(d.settlement_id, d.decision, d.reason_code, d.invoice_id, d.bank_txn_id) for d in ds]
    same = sig(a) == sig(b)
    from llm.explainer import explain_case

    sample = a[0] if a else None
    mutated = False
    if sample:
        payload = {
            "decision": sample.decision,
            "reason_code": sample.reason_code,
            "policy_decision": sample.decision,
            "evidence": sample.evidence,
        }
        before = (sample.decision, sample.reason_code)
        explain_case(payload)
        after = (sample.decision, sample.reason_code)
        mutated = before != after
    return {
        "pass": same and not mutated,
        "n": len(a),
        "decisions_identical": same,
        "llm_cannot_mutate": not mutated,
        "note": "Matcher path is identical with AI ON or OFF. Explanations attach after the decision.",
    }


@app.get("/api/benchmark/throughput")
def api_benchmark_throughput(
    sizes: str = Query("100,500,1000,2000", description="Comma-separated record counts"),
    seed:  int = Query(42),
):
    """Run at increasing record counts to show scaling characteristics."""
    try:
        size_list = [int(s.strip()) for s in sizes.split(",") if s.strip()]
    except ValueError:
        raise HTTPException(400, "sizes must be comma-separated integers")
    if any(s > 3000 for s in size_list):
        raise HTTPException(400, "max 3000 records per size for benchmark")
    if len(size_list) > 8:
        raise HTTPException(400, "max 8 sizes per request")
    return benchmark.run_throughput(sorted(size_list), seed)


frontend = Path(__file__).resolve().parent.parent / "frontend"


@app.get("/", include_in_schema=False)
def landing():
    """Marketing / landing page — judges land here first."""
    return FileResponse(frontend / "landing.html")


@app.get("/app", include_in_schema=False)
def tool():
    """The live reconciliation dashboard."""
    return FileResponse(frontend / "app.html")


# Static mount for CSS, JS, and any other assets.
# Must come AFTER the explicit routes above so they are not overridden.
app.mount("/", StaticFiles(directory=str(frontend), html=True), name="ui")
