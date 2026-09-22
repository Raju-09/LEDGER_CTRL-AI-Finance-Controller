import json
from api.webhook_dispatcher import AnomalyWebhookDispatcher

def test_webhook_payload_format():
    payload_str = AnomalyWebhookDispatcher.format_alert_payload({"tx_id": "TX99", "severity": "HIGH"})
    data = json.loads(payload_str)
    assert data["event"] == "FINANCIAL_ANOMALY_FLAGGED"
    assert data["severity"] == "HIGH"
