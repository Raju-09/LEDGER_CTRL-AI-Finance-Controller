from typing import List, Dict

class ReconciliationRuleEvaluator:
    @staticmethod
    def calculate_metrics(y_true: List[int], y_pred: List[int]) -> Dict[str, float]:
        tp = sum(1 for t, p in zip(y_true, y_pred) if t == 1 and p == 1)
        fp = sum(1 for t, p in zip(y_true, y_pred) if t == 0 and p == 1)
        fn = sum(1 for t, p in zip(y_true, y_pred) if t == 1 and p == 0)
        precision = tp / (tp + fp) if (tp + fp) > 0 else 0.0
        recall = tp / (tp + fn) if (tp + fn) > 0 else 0.0
        return {"precision": round(precision, 4), "recall": round(recall, 4)}
