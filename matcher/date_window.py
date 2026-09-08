from datetime import datetime, timedelta

class DateProximityMatcher:
    @staticmethod
    def is_within_window(date_str1: str, date_str2: str, max_days: int = 3) -> bool:
        d1 = datetime.fromisoformat(date_str1[:10])
        d2 = datetime.fromisoformat(date_str2[:10])
        return abs((d1 - d2).days) <= max_days
