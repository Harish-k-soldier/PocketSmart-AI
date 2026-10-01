from app.services.formatting import format_inr


def test_basic_grouping():
    assert format_inr(1234) == "₹1,234"
    assert format_inr(100000) == "₹1,00,000"
    assert format_inr(12345678) == "₹1,23,45,678"


def test_zero_and_small():
    assert format_inr(0) == "₹0"
    assert format_inr(5) == "₹5"
    assert format_inr(999) == "₹999"


def test_negative():
    assert format_inr(-5000) == "-₹5,000"
    assert format_inr(-12345678) == "-₹1,23,45,678"


def test_none_nan_strings():
    assert format_inr(None) == "₹0"
    assert format_inr(float("nan")) == "₹0"
    assert format_inr("abc") == "₹0"
    assert format_inr("") == "₹0"


def test_rounding():
    assert format_inr(100.6) == "₹101"
    assert format_inr(100.4) == "₹100"
