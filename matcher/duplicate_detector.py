from typing import List, Dict, Set

class DuplicateChargeDetector:
    @staticmethod
    def find_duplicates(transactions: List[Dict]) -> List[Dict]:
        seen: Set[str] = set()
        duplicates = []
        for tx in transactions:
            key = f"{tx.get('merchant')}_{tx.get('amount')}_{tx.get('date')[:10]}"
            if key in seen:
                duplicates.append(tx)
            else:
                seen.add(key)
        return duplicates
