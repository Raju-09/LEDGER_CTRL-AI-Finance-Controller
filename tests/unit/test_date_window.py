from matcher.date_window import DateProximityMatcher

def test_within_window():
    assert DateProximityMatcher.is_within_window("2026-09-01", "2026-09-03", max_days=3) is True

def test_outside_window():
    assert DateProximityMatcher.is_within_window("2026-09-01", "2026-09-06", max_days=3) is False
