from decimal import Decimal

from app.money import dsum, money, split_by_percentages
from app.services.payments import compute_amounts


def test_money_quantizes():
    assert money("1000") == Decimal("1000.00")
    assert money("1000.005") == Decimal("1000.01")  # half-up


def test_split_exact_35_65():
    split = split_by_percentages(
        Decimal("1000.00"), [(1, Decimal("35")), (2, Decimal("65"))]
    )
    assert split[1] == Decimal("350.00")
    assert split[2] == Decimal("650.00")
    assert dsum(split.values()) == Decimal("1000.00")


def test_split_absorbs_rounding():
    # 33.33% x3 sobre 100 -> el último absorbe el centavo
    split = split_by_percentages(
        Decimal("100.00"),
        [(1, Decimal("33.33")), (2, Decimal("33.33")), (3, Decimal("33.34"))],
    )
    assert dsum(split.values()) == Decimal("100.00")


def test_compute_amounts_usd():
    r = compute_amounts(
        currency_charged="USD", amount_original=Decimal("1000"), exchange_rate=Decimal("1300")
    )
    assert r.amount_usd == Decimal("1000.00")
    assert r.amount_ars == Decimal("1300000.00")


def test_compute_amounts_ars():
    r = compute_amounts(
        currency_charged="ARS", amount_original=Decimal("650000"), exchange_rate=Decimal("1300")
    )
    assert r.amount_ars == Decimal("650000.00")
    assert r.amount_usd == Decimal("500.00")


def test_compute_amounts_rejects_zero_rate():
    import pytest

    with pytest.raises(ValueError):
        compute_amounts(
            currency_charged="USD", amount_original=Decimal("10"), exchange_rate=Decimal("0")
        )
