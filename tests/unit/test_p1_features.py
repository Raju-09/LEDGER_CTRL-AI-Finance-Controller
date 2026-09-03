"""Unit tests for importer and benchmark endpoints."""
from api.importer import process_upload, session_summary
from api.benchmark import run_seeds, run_throughput

def test_importer_process_csv():
    settlements_csv = b"settlement_id,amount,date,vendor,reference\nS001,1500.00,2026-08-20,Razorpay,UTR123456\n"
    bank_csv = b"txn_id,amount,date,narration,reference\nB001,1500.00,2026-08-20,NEFT Razorpay UTR123456,UTR123456\n"
    invoices_csv = b"invoice_id,amount,due_date,vendor,invoice_number\nI001,1500.00,2026-08-20,Razorpay,INV-001\n"

    sess = process_upload(settlements_csv, "settlements.csv", bank_csv, "bank.csv", invoices_csv, "invoices.csv")
    assert sess.is_complete is True
    assert len(sess.models_s) == 1
    assert len(sess.models_b) == 1
    assert len(sess.models_i) == 1

    summary = session_summary(sess)
    assert summary["counts"]["settlements"] == 1
    assert summary["settlements"]["total_rows"] == 1
    assert summary["settlements"]["valid_rows"] == 1


def test_benchmark_seeds():
    res = run_seeds([42, 847], n=20)
    assert len(res) == 3  # 2 seeds + MEAN row
    assert res[0]["seed"] == 42
    assert res[1]["seed"] == 847
    assert res[2]["seed"] == "MEAN"
    assert res[0]["precision"] > 0.8


def test_benchmark_throughput():
    res = run_throughput([50, 100], seed=42)
    assert len(res) == 2
    assert res[0]["n"] > 0
    assert res[0]["blocking_reduction"] > 0.4
