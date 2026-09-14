from matcher.duplicate_detector import DuplicateChargeDetector

def test_duplicate_charge_detection():
    txs = [
        {"merchant": "SaaS Corp", "amount": 99.0, "date": "2026-09-14T10:00:00"},
        {"merchant": "SaaS Corp", "amount": 99.0, "date": "2026-09-14T10:05:00"},
        {"merchant": "Coffee Shop", "amount": 4.5, "date": "2026-09-14T11:00:00"}
    ]
    dupes = DuplicateChargeDetector.find_duplicates(txs)
    assert len(dupes) == 1
    assert dupes[0]["merchant"] == "SaaS Corp"
