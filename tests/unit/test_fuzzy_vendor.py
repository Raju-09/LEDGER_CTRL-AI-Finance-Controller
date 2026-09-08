from matcher.fuzzy_vendor import FuzzyVendorMatcher

def test_fuzzy_vendor_match():
    score = FuzzyVendorMatcher.similarity("Amazon Web Services Inc", "Amazon Web Services")
    assert score >= 0.75

def test_fuzzy_vendor_mismatch():
    score = FuzzyVendorMatcher.similarity("Google Cloud", "Microsoft Azure")
    assert score == 0.0
