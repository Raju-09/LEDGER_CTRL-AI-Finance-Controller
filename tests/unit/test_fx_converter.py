from decimal import Decimal
import pytest
from matcher.fx_converter import MultiCurrencyFXConverter

def test_same_currency_identity():
    converter = MultiCurrencyFXConverter()
    amount = Decimal("100.50")
    assert converter.convert(amount, "USD", "USD") == amount

def test_currency_conversion():
    converter = MultiCurrencyFXConverter()
    eur_amount = Decimal("100.00")
    usd_val = converter.convert(eur_amount, "EUR", "USD")
    assert usd_val == Decimal("108.00")

def test_unsupported_currency_raises():
    converter = MultiCurrencyFXConverter()
    with pytest.raises(ValueError):
        converter.convert(Decimal("100"), "XYZ", "USD")
