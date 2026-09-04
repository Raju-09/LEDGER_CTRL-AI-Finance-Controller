from models.audit_log import TransactionAuditLog

def test_audit_log_creation():
    log = TransactionAuditLog(tx_id="TX_99", reconciled_by="auto_matcher", status="MATCHED", amount=450.0)
    assert log.tx_id == "TX_99"
    assert len(log.audit_id) == 36
