from __future__ import annotations

from pathlib import Path

from sqlalchemy import (
    JSON,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    create_engine,
    event,
    func,
    text,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, sessionmaker

from config import settings


class Base(DeclarativeBase):
    pass


class Batch(Base):
    __tablename__ = "batches"
    id: Mapped[str] = mapped_column(String, primary_key=True)
    seed: Mapped[int] = mapped_column(Integer)
    n: Mapped[int] = mapped_column(Integer)
    split: Mapped[str] = mapped_column(String)  # dev | holdout
    created_at: Mapped[str] = mapped_column(DateTime, server_default=func.now())
    status: Mapped[str] = mapped_column(String, default="generated")


class SettlementRow(Base):
    __tablename__ = "settlements"
    settlement_id: Mapped[str] = mapped_column(String, primary_key=True)
    batch_id: Mapped[str] = mapped_column(String, ForeignKey("batches.id"), index=True)
    amount: Mapped[float] = mapped_column(Float)
    currency: Mapped[str] = mapped_column(String)
    date: Mapped[str] = mapped_column(Date)
    vendor_name_raw: Mapped[str] = mapped_column(String)
    reference_id: Mapped[str] = mapped_column(String)
    fee: Mapped[float] = mapped_column(Float)
    tax: Mapped[float] = mapped_column(Float)
    invoice_number: Mapped[str] = mapped_column(String, default="")
    txn_type: Mapped[str] = mapped_column(String, default="PAYMENT")


class BankRow(Base):
    __tablename__ = "bank_statements"
    txn_id: Mapped[str] = mapped_column(String, primary_key=True)
    batch_id: Mapped[str] = mapped_column(String, ForeignKey("batches.id"), index=True)
    amount: Mapped[float] = mapped_column(Float)
    date: Mapped[str] = mapped_column(Date)
    narration_raw: Mapped[str] = mapped_column(String)
    reference: Mapped[str] = mapped_column(String)
    currency: Mapped[str] = mapped_column(String, default="INR")
    txn_type: Mapped[str] = mapped_column(String, default="PAYMENT")


class InvoiceRow(Base):
    __tablename__ = "invoices"
    invoice_id: Mapped[str] = mapped_column(String, primary_key=True)
    batch_id: Mapped[str] = mapped_column(String, ForeignKey("batches.id"), index=True)
    amount: Mapped[float] = mapped_column(Float)
    currency: Mapped[str] = mapped_column(String)
    due_date: Mapped[str] = mapped_column(Date)
    vendor_name_raw: Mapped[str] = mapped_column(String)
    invoice_number: Mapped[str] = mapped_column(String)
    txn_type: Mapped[str] = mapped_column(String, default="PAYMENT")


class GroundTruthDB(Base):
    __tablename__ = "ground_truth"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    batch_id: Mapped[str] = mapped_column(String, ForeignKey("batches.id"), index=True)
    true_group_id: Mapped[str] = mapped_column(String)
    settlement_id: Mapped[str] = mapped_column(String, index=True)
    invoice_id: Mapped[str | None] = mapped_column(String, nullable=True)
    bank_txn_id: Mapped[str | None] = mapped_column(String, nullable=True)
    corruption: Mapped[str] = mapped_column(String)
    notes: Mapped[str] = mapped_column(Text, default="")


class MatchResultRow(Base):
    __tablename__ = "match_results"
    match_id: Mapped[str] = mapped_column(String, primary_key=True)
    batch_id: Mapped[str] = mapped_column(String, ForeignKey("batches.id"), index=True)
    run_id: Mapped[str] = mapped_column(String, index=True)
    settlement_id: Mapped[str] = mapped_column(String, index=True)
    invoice_id: Mapped[str | None] = mapped_column(String, nullable=True)
    bank_txn_id: Mapped[str | None] = mapped_column(String, nullable=True)
    match_type: Mapped[str] = mapped_column(String)
    confidence: Mapped[float] = mapped_column(Float)
    decision: Mapped[str] = mapped_column(String, index=True)
    reason_code: Mapped[str] = mapped_column(String, index=True)
    evidence: Mapped[dict] = mapped_column(JSON)
    llm_suggestion: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    decided_at: Mapped[str] = mapped_column(DateTime, server_default=func.now())


class AuditEvent(Base):
    __tablename__ = "audit_events"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    run_id: Mapped[str] = mapped_column(String, index=True)
    batch_id: Mapped[str] = mapped_column(String, index=True)
    settlement_id: Mapped[str] = mapped_column(String, index=True)
    record_ids: Mapped[list] = mapped_column(JSON)
    evidence_snapshot: Mapped[dict] = mapped_column(JSON)
    decision: Mapped[str] = mapped_column(String)
    reason_code: Mapped[str] = mapped_column(String)
    timestamp: Mapped[str] = mapped_column(DateTime, server_default=func.now())


class EvalRun(Base):
    __tablename__ = "eval_runs"
    run_id: Mapped[str] = mapped_column(String, primary_key=True)
    batch_id: Mapped[str] = mapped_column(String, index=True)
    metrics: Mapped[dict] = mapped_column(JSON)
    elapsed_ms: Mapped[float] = mapped_column(Float)
    created_at: Mapped[str] = mapped_column(DateTime, server_default=func.now())


def get_engine(path: str | None = None):
    db_path = Path(path or settings.db_path)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    engine = create_engine(
        f"sqlite:///{db_path}",
        echo=False,
        connect_args={
            "check_same_thread": False,  # FastAPI serves requests from a thread pool
            "timeout": 20,               # Wait up to 20 s instead of failing immediately
        },
    )

    @event.listens_for(engine, "connect")
    def _set_wal_mode(dbapi_conn, _):
        """Enable WAL journal mode once per new connection.

        WAL allows concurrent readers during an active write, which is the
        common pattern here: reconcile (write) + UI polling (read).  Without
        WAL, SQLite serialises all access and raises OperationalError on the
        second concurrent request.
        """
        dbapi_conn.execute("PRAGMA journal_mode=WAL")
        dbapi_conn.execute("PRAGMA synchronous=NORMAL")  # safe with WAL; faster than FULL

    return engine


SessionLocal = sessionmaker(autocommit=False, autoflush=False)


def init_db(path: str | None = None):
    engine = get_engine(path)
    Base.metadata.create_all(engine)
    _migrate(engine)
    SessionLocal.configure(bind=engine)
    return engine


def _migrate(engine) -> None:
    specs = [
        ("settlements", "txn_type", "VARCHAR DEFAULT 'PAYMENT'"),
        ("bank_statements", "txn_type", "VARCHAR DEFAULT 'PAYMENT'"),
        ("invoices", "txn_type", "VARCHAR DEFAULT 'PAYMENT'"),
    ]
    with engine.begin() as conn:
        for table, col, ddl in specs:
            rows = conn.execute(text(f"PRAGMA table_info({table})")).fetchall()
            names = {r[1] for r in rows}
            if rows and col not in names:
                conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {col} {ddl}"))
