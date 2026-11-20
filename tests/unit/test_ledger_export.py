import json
from matcher.ledger_export import LedgerAuditExporter

def test_ledger_export_json():
    data = [{"tx_id": "TX100", "status": "MATCHED", "amount": 250.0}]
    json_str = LedgerAuditExporter.export_json(data)
    loaded = json.loads(json_str)
    assert loaded["record_count"] == 1
    assert loaded["audit_ledger"][0]["tx_id"] == "TX100"

def test_ledger_export_csv():
    data = [{"tx_id": "TX101", "status": "FLAGGED", "amount": 100.0}]
    csv_str = LedgerAuditExporter.export_csv(data)
    assert "tx_id,status,amount" in csv_str
    assert "TX101,FLAGGED,100.0" in csv_str
