from typing import List, Dict, Generator

class BatchReconciliationEngine:
    @staticmethod
    def process_stream(transactions: List[Dict]) -> Generator[Dict, None, None]:
        for tx in transactions:
            yield {
                "tx_id": tx.get("id"),
                "status": "PROCESSED",
                "matched": tx.get("amount", 0) > 0
            }
