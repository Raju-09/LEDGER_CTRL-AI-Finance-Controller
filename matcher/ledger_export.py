import csv
import json
from io import StringIO
from typing import List, Dict, Any

class LedgerAuditExporter:
    @staticmethod
    def export_csv(records: List[Dict[str, Any]]) -> str:
        if not records:
            return ""
        output = StringIO()
        fieldnames = list(records[0].keys())
        writer = csv.DictWriter(output, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(records)
        return output.getvalue()

    @staticmethod
    def export_json(records: List[Dict[str, Any]]) -> str:
        return json.dumps({"audit_ledger": records, "record_count": len(records)}, indent=2)
