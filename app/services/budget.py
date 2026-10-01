"""Deterministic budget math: largest-remainder splits and allocations.

All arithmetic is integer-only. Percentage splits use the largest-remainder
method so the parts always sum exactly to the total (no off-by-one rupee).
"""

import math
from typing import Iterable, Sequence

CONTINGENCY_PERCENT = 5


def contingency_amount(budget: int) -> int:
    """5% contingency buffer, rounded to the nearest rupee."""
    return int(round(budget * CONTINGENCY_PERCENT / 100))


def allocatable_amount(budget: int) -> int:
    """Budget left after reserving the contingency buffer."""
    return budget - contingency_amount(budget)


def largest_remainder_split(total: int, weights: Sequence[float]) -> list[int]:
    """Split `total` into len(weights) integer parts proportional to weights.

    Uses the largest-remainder method so parts sum exactly to `total`.
    All parts are non-negative. Returns [0, 0, ...] for empty weights.
    """
    if not weights:
        return []
    if total < 0:
        raise ValueError("total must be non-negative")
    clean = [max(0.0, float(w)) for w in weights]
    weight_sum = sum(clean)
    if weight_sum <= 0:
        clean = [1.0] * len(clean)
        weight_sum = float(len(clean))

    exact = [total * w / weight_sum for w in clean]
    floors = [math.floor(e) for e in exact]
    remainder = total - sum(floors)
    # Distribute the leftover rupees to the largest fractional remainders.
    order = sorted(range(len(exact)), key=lambda i: exact[i] - floors[i], reverse=True)
    for i in order[:remainder]:
        floors[i] += 1
    return floors


def percent_used(total_spent: int, budget_total: int) -> float:
    if budget_total <= 0:
        return 0.0
    return round(total_spent * 100.0 / budget_total, 1)


def per_guest_cost(total_spent: int, guests: int) -> int:
    if guests <= 0:
        return 0
    return int(round(total_spent / guests))


def ceil_div(a: int, b: int) -> int:
    if b <= 0:
        raise ValueError("divisor must be positive")
    return -(-a // b)


def normalize_weights(weights: Iterable[float]) -> list[float]:
    """Scale weights so they sum to 100 (used for percentage display)."""
    vals = [max(0.0, float(w)) for w in weights]
    total = sum(vals)
    if total <= 0:
        return [0.0] * len(vals)
    return [w * 100.0 / total for w in vals]
