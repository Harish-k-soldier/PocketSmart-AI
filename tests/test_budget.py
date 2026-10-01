import random

from app.services.budget import (
    allocatable_amount,
    contingency_amount,
    largest_remainder_split,
    per_guest_cost,
    percent_used,
)


def test_largest_remainder_sums_exactly():
    rng = random.Random(42)
    for _ in range(500):
        total = rng.randint(0, 10_000_000)
        n = rng.randint(1, 8)
        weights = [rng.randint(0, 20) for _ in range(n)]
        parts = largest_remainder_split(total, weights)
        assert sum(parts) == total
        assert all(p >= 0 for p in parts)
        assert len(parts) == n


def test_largest_remainder_proportional():
    parts = largest_remainder_split(100, [1, 1, 1])
    assert parts == [34, 33, 33]
    parts = largest_remainder_split(100, [50, 25, 25])
    assert parts == [50, 25, 25]


def test_largest_remainder_zero_weights():
    assert sum(largest_remainder_split(100, [0, 0, 0])) == 100
    assert largest_remainder_split(0, [1, 2, 3]) == [0, 0, 0]
    assert largest_remainder_split(100, []) == []


def test_contingency_is_five_percent():
    assert contingency_amount(150000) == 7500
    assert contingency_amount(10000) == 500
    assert allocatable_amount(150000) == 142500


def test_percent_used():
    assert percent_used(118400, 150000) == 78.9
    assert percent_used(0, 100) == 0.0
    assert percent_used(100, 0) == 0.0


def test_per_guest_cost():
    assert per_guest_cost(52000, 100) == 520
    assert per_guest_cost(0, 0) == 0
    assert per_guest_cost(100, 3) == 33
