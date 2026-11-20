from matcher.benford_audit import BenfordForensicAuditor

def test_extract_first_digit():
    assert BenfordForensicAuditor.extract_first_digit(192.45) == 1
    assert BenfordForensicAuditor.extract_first_digit(0.0054) == 5
    assert BenfordForensicAuditor.extract_first_digit(9.99) == 9

def test_benford_chi_square_uniform_anomaly():
    # Artificially created uniform amounts should trigger anomaly
    amounts = [float(i * 100 + 50) for i in range(1, 10)] * 30
    res = BenfordForensicAuditor.compute_chi_square_divergence(amounts)
    assert res["is_anomaly"] is True
