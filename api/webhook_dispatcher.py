import json
from typing import Dict, Any

class AnomalyWebhookDispatcher:
    @staticmethod
    def format_alert_payload(alert_data: Dict[str, Any]) -> str:
        return json.dumps({
            "event": "FINANCIAL_ANOMALY_FLAGGED",
            "severity": alert_data.get("severity", "MEDIUM"),
            "details": alert_data
        })
