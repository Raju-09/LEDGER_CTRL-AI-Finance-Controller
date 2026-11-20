from typing import Dict, Optional
from decimal import Decimal, ROUND_HALF_UP

class MultiCurrencyFXConverter:
    DEFAULT_RATES: Dict[str, Decimal] = {
        "USD": Decimal("1.00"),
        "EUR": Decimal("1.08"),
        "GBP": Decimal("1.27"),
        "INR": Decimal("0.012"),
        "JPY": Decimal("0.0065")
    }

    def __init__(self, custom_rates: Optional[Dict[str, Decimal]] = None):
        self.rates = self.DEFAULT_RATES.copy()
        if custom_rates:
            self.rates.update(custom_rates)

    def convert(self, amount: Decimal, from_curr: str, to_curr: str = "USD") -> Decimal:
        if from_curr == to_curr:
            return amount
        if from_curr not in self.rates or to_curr not in self.rates:
            raise ValueError(f"Unsupported currency pair: {from_curr} -> {to_curr}")

        # Convert to base USD then to target currency
        amount_usd = amount * self.rates[from_curr]
        target_amount = amount_usd / self.rates[to_curr]
        return target_amount.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
