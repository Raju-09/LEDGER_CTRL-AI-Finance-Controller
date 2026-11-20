import math
from typing import List, Dict

class BenfordForensicAuditor:
    # Theoretical Benford's Law distribution for first digits (1 to 9)
    BENFORD_PROBABILITIES: Dict[int, float] = {
        d: math.log10(1 + 1 / d) for d in range(1, 10)
    }

    @classmethod
    def extract_first_digit(cls, amount: float) -> int:
        amt = abs(amount)
        if amt == 0:
            return 0
        s = f"{amt:.10f}".replace(".", "").lstrip("0")
        return int(s[0]) if s else 0

    @classmethod
    def compute_chi_square_divergence(cls, amounts: List[float]) -> Dict[str, float]:
        valid_digits = [cls.extract_first_digit(a) for a in amounts if cls.extract_first_digit(a) > 0]
        n = len(valid_digits)
        if n < 10:
            return {"chi_square": 0.0, "p_value_heuristic": 1.0, "is_anomaly": False}

        counts = {d: 0 for d in range(1, 10)}
        for d in valid_digits:
            counts[d] += 1

        chi_sq = 0.0
        for d in range(1, 10):
            observed = counts[d]
            expected = n * cls.BENFORD_PROBABILITIES[d]
            chi_sq += ((observed - expected) ** 2) / expected

        # Chi-square critical value for 8 degrees of freedom at alpha=0.05 is 15.51
        is_anomaly = chi_sq > 15.51
        return {
            "chi_square": round(chi_sq, 4),
            "sample_size": n,
            "is_anomaly": is_anomaly
        }
