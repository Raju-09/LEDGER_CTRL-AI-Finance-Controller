from matcher.split_transaction import SplitTransactionResolver

def test_split_transaction_match():
    assert SplitTransactionResolver.match_subcomponents(100.0, [40.0, 35.0, 25.0]) is True

def test_split_transaction_mismatch():
    assert SplitTransactionResolver.match_subcomponents(100.0, [40.0, 30.0]) is False
