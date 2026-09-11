from typing import List

class SplitTransactionResolver:
    @staticmethod
    def match_subcomponents(target_amount: float, item_amounts: List[float], tolerance: float = 0.01) -> bool:
        return abs(target_amount - sum(item_amounts)) <= tolerance
