from typing import Dict, Any

class ExtractionConfidenceScorer:
    @staticmethod
    def score_extraction(data: Dict[str, Any]) -> float:
        required = ["merchant", "amount", "currency", "date"]
        present = sum(1 for f in required if data.get(f) is not None)
        return round(present / len(required), 2)
