from api.batch_reconciler import BatchReconciliationEngine

def test_batch_reconciliation_streaming():
    txs = [{"id": f"TX_{i}", "amount": float(i * 10)} for i in range(10)]
    stream = list(BatchReconciliationEngine.process_stream(txs))
    assert len(stream) == 10
    assert stream[0]["tx_id"] == "TX_0"
