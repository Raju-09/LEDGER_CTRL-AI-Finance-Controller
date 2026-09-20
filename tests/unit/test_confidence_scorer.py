from llm.confidence_scorer import ExtractionConfidenceScorer

def test_perfect_score():
    data = {"merchant": "AWS", "amount": 100.0, "currency": "USD", "date": "2026-09-20"}
    assert ExtractionConfidenceScorer.score_extraction(data) == 1.0

def test_partial_score():
    data = {"merchant": "AWS", "amount": 100.0}
    assert ExtractionConfidenceScorer.score_extraction(data) == 0.5
