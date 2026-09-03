from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

from sqlalchemy import delete, select

from db.schema import (
    AuditEvent,
    BankRow,
    Batch,
    EvalRun,
    GroundTruthDB,
    InvoiceRow,
    MatchResultRow,
    SessionLocal,
    SettlementRow,
)
from config import settings
from models import BankStatement, Decision, GroundTruthRow, Invoice, Settlement


class Store:
    def __init__(self, session=None):
        self.s = session or SessionLocal()

    def close(self):
        self.s.close()

    def create_batch(
        self,
        batch_id: str,
        seed: int,
        n: int,
        split: str,
        settlements: list[Settlement],
        invoices: list[Invoice],
        banks: list[BankStatement],
        truth: list[GroundTruthRow],
    ) -> None:
        self.s.add(Batch(id=batch_id, seed=seed, n=n, split=split, status="generated"))
        for x in settlements:
            self.s.add(
                SettlementRow(
                    settlement_id=x.settlement_id,
                    batch_id=batch_id,
                    amount=x.amount,
                    currency=x.currency,
                    date=x.date,
                    vendor_name_raw=x.vendor_name_raw,
                    reference_id=x.reference_id,
                    fee=x.fee,
                    tax=x.tax,
                    invoice_number=x.invoice_number,
                    txn_type=getattr(x, "txn_type", "PAYMENT") or "PAYMENT",
                )
            )
        for x in invoices:
            self.s.add(
                InvoiceRow(
                    invoice_id=x.invoice_id,
                    batch_id=batch_id,
                    amount=x.amount,
                    currency=x.currency,
                    due_date=x.due_date,
                    vendor_name_raw=x.vendor_name_raw,
                    invoice_number=x.invoice_number,
                    txn_type=getattr(x, "txn_type", "PAYMENT") or "PAYMENT",
                )
            )
        for x in banks:
            self.s.add(
                BankRow(
                    txn_id=x.txn_id,
                    batch_id=batch_id,
                    amount=x.amount,
                    date=x.date,
                    narration_raw=x.narration_raw,
                    reference=x.reference,
                    currency=x.currency,
                    txn_type=getattr(x, "txn_type", "PAYMENT") or "PAYMENT",
                )
            )
        for t in truth:
            self.s.add(
                GroundTruthDB(
                    batch_id=batch_id,
                    true_group_id=t.true_group_id,
                    settlement_id=t.settlement_id,
                    invoice_id=t.invoice_id,
                    bank_txn_id=t.bank_txn_id,
                    corruption=t.corruption,
                    notes=t.notes,
                )
            )
        self.s.commit()

    def load_sources(self, batch_id: str) -> tuple[list[Settlement], list[Invoice], list[BankStatement]]:
        settlements = [
            Settlement(
                settlement_id=r.settlement_id,
                amount=r.amount,
                currency=r.currency,
                date=r.date,
                vendor_name_raw=r.vendor_name_raw,
                reference_id=r.reference_id,
                fee=r.fee,
                tax=r.tax,
                batch_id=batch_id,
                invoice_number=r.invoice_number or "",
                txn_type=getattr(r, "txn_type", None) or "PAYMENT",
            )
            for r in self.s.scalars(select(SettlementRow).where(SettlementRow.batch_id == batch_id))
        ]
        invoices = [
            Invoice(
                invoice_id=r.invoice_id,
                amount=r.amount,
                currency=r.currency,
                due_date=r.due_date,
                vendor_name_raw=r.vendor_name_raw,
                invoice_number=r.invoice_number,
                batch_id=batch_id,
                txn_type=getattr(r, "txn_type", None) or "PAYMENT",
            )
            for r in self.s.scalars(select(InvoiceRow).where(InvoiceRow.batch_id == batch_id))
        ]
        banks = [
            BankStatement(
                txn_id=r.txn_id,
                amount=r.amount,
                date=r.date,
                narration_raw=r.narration_raw,
                reference=r.reference,
                currency=r.currency,
                batch_id=batch_id,
                txn_type=getattr(r, "txn_type", None) or "PAYMENT",
            )
            for r in self.s.scalars(select(BankRow).where(BankRow.batch_id == batch_id))
        ]
        return settlements, invoices, banks

    def load_truth(self, batch_id: str) -> list[GroundTruthRow]:
        rows = self.s.scalars(select(GroundTruthDB).where(GroundTruthDB.batch_id == batch_id))
        return [
            GroundTruthRow(
                true_group_id=r.true_group_id,
                settlement_id=r.settlement_id,
                invoice_id=r.invoice_id,
                bank_txn_id=r.bank_txn_id,
                corruption=r.corruption,
                notes=r.notes or "",
            )
            for r in rows
        ]

    def persist_run(self, batch_id: str, decisions: list[Decision], metrics: dict, elapsed_ms: float) -> str:
        batch = self.s.get(Batch, batch_id)
        seed = batch.seed if batch else 0
        split = batch.split if batch else "holdout"
        n = len(decisions)
        run_id = f"RUN-{seed}-{split[:1].upper()}-{n}-{batch_id[-4:].upper()}"
        metrics = dict(metrics or {})
        metrics["run_id"] = run_id
        lineage = dict(metrics.get("lineage") or {})
        lineage["run_id"] = run_id
        lineage["batch_id"] = batch_id
        lineage["seed"] = seed
        lineage["split"] = split
        lineage["n"] = n
        metrics["lineage"] = lineage
        now = datetime.now(timezone.utc)
        # idempotent re-run: drop prior match/audit for this batch
        self.s.execute(delete(MatchResultRow).where(MatchResultRow.batch_id == batch_id))
        self.s.execute(delete(AuditEvent).where(AuditEvent.batch_id == batch_id))
        self.s.execute(delete(EvalRun).where(EvalRun.batch_id == batch_id))

        for d in decisions:
            match_id = f"M-{d.settlement_id}"
            self.s.add(
                MatchResultRow(
                    match_id=match_id,
                    batch_id=batch_id,
                    run_id=run_id,
                    settlement_id=d.settlement_id,
                    invoice_id=d.invoice_id,
                    bank_txn_id=d.bank_txn_id,
                    match_type=d.match_type,
                    confidence=d.confidence,
                    decision=d.decision,
                    reason_code=d.reason_code,
                    evidence=d.evidence,
                    llm_suggestion=d.llm_suggestion,
                    decided_at=now,
                )
            )
            ids = [d.settlement_id]
            if d.invoice_id:
                ids.append(d.invoice_id)
            if d.bank_txn_id:
                ids.append(d.bank_txn_id)
            self.s.add(
                AuditEvent(
                    run_id=run_id,
                    batch_id=batch_id,
                    settlement_id=d.settlement_id,
                    record_ids=ids,
                    evidence_snapshot={
                        **d.evidence,
                        "confidence": d.confidence,
                        "match_type": d.match_type,
                        "invoice_id": d.invoice_id,
                        "bank_txn_id": d.bank_txn_id,
                        "llm_suggestion": d.llm_suggestion,
                        "matcher_version": settings.matcher_version,
                        "policy_version": settings.policy_version,
                        "run_id": run_id,
                    },
                    decision=d.decision,
                    reason_code=d.reason_code,
                    timestamp=now,
                )
            )
        self.s.add(EvalRun(run_id=run_id, batch_id=batch_id, metrics=metrics, elapsed_ms=elapsed_ms, created_at=now))
        batch = self.s.get(Batch, batch_id)
        if batch:
            batch.status = "reconciled"
        self.s.commit()
        return run_id

    def get_batch(self, batch_id: str) -> Batch | None:
        return self.s.get(Batch, batch_id)

    def list_batches(self, limit: int = 20) -> list[Batch]:
        return list(self.s.scalars(select(Batch).order_by(Batch.created_at.desc()).limit(limit)))

    def matches(self, batch_id: str) -> list[MatchResultRow]:
        return list(self.s.scalars(select(MatchResultRow).where(MatchResultRow.batch_id == batch_id)))

    def exceptions(self, batch_id: str, min_amount: float = 0.0) -> list[dict]:
        q = (
            select(MatchResultRow, SettlementRow)
            .join(SettlementRow, SettlementRow.settlement_id == MatchResultRow.settlement_id)
            .where(MatchResultRow.batch_id == batch_id)
            .where(MatchResultRow.decision.in_(["escalate", "unresolved"]))
        )
        out = []
        for m, s in self.s.execute(q):
            if s.amount < min_amount:
                continue
            out.append(
                {
                    "settlement_id": m.settlement_id,
                    "amount": s.amount,
                    "vendor": s.vendor_name_raw,
                    "decision": m.decision,
                    "reason_code": m.reason_code,
                    "confidence": m.confidence,
                    "invoice_id": m.invoice_id,
                    "bank_txn_id": m.bank_txn_id,
                    "evidence": m.evidence,
                    "llm_suggestion": m.llm_suggestion,
                }
            )
        out.sort(key=lambda r: r["amount"], reverse=True)
        return out

    def audit_for(self, settlement_id: str) -> list[AuditEvent]:
        return list(
            self.s.scalars(select(AuditEvent).where(AuditEvent.settlement_id == settlement_id).order_by(AuditEvent.id.desc()))
        )

    def latest_eval(self, batch_id: str) -> EvalRun | None:
        return self.s.scalars(select(EvalRun).where(EvalRun.batch_id == batch_id).order_by(EvalRun.created_at.desc())).first()

    def eval_by_run(self, run_id: str) -> EvalRun | None:
        return self.s.get(EvalRun, run_id)

    def matches_for_run(self, run_id: str) -> list[MatchResultRow]:
        return list(self.s.scalars(select(MatchResultRow).where(MatchResultRow.run_id == run_id)))

    def settlement(self, settlement_id: str) -> SettlementRow | None:
        return self.s.get(SettlementRow, settlement_id)
