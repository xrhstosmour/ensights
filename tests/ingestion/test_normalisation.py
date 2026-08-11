"""Unit tests for shared ingestion parsing rules."""

from __future__ import annotations

from decimal import Decimal

from app.ingestion.normalisation import parse_decimal
from app.ingestion.normalisation import parse_int


class TestParseDecimal:
    """Tests for parse_decimal()."""

    def test_plain_dot_decimal(self) -> None:
        """A plain dot-decimal value parses as-is."""
        assert parse_decimal("4.50") == Decimal("4.50")

    def test_comma_as_european_decimal_point(self) -> None:
        """A lone comma followed by 1-2 digits is a decimal point, not grouping."""
        assert parse_decimal("4,50") == Decimal("4.50")
        assert parse_decimal("4,5") == Decimal("4.5")

    def test_comma_as_thousands_grouping(self) -> None:
        """A lone comma followed by 3 digits is thousands grouping."""
        assert parse_decimal("1,234") == Decimal("1234")

    def test_multiple_thousands_groups(self) -> None:
        """Multiple grouping commas are all stripped."""
        assert parse_decimal("1,234,567") == Decimal("1234567")

    def test_comma_grouping_with_dot_decimal(self) -> None:
        """Comma grouping alongside a dot decimal point parses correctly."""
        assert parse_decimal("1,234.56") == Decimal("1234.56")

    def test_blank_returns_none(self) -> None:
        """An empty or whitespace-only value returns None."""
        assert parse_decimal("") is None
        assert parse_decimal("   ") is None

    def test_malformed_returns_none(self) -> None:
        """A malformed value returns None instead of raising."""
        assert parse_decimal("not-a-number") is None

    def test_nan_string_rejected(self) -> None:
        """A NaN value must not reach downstream comparisons."""
        assert parse_decimal("NaN") is None

    def test_infinity_string_rejected(self) -> None:
        """An Infinity value must not reach downstream arithmetic."""
        assert parse_decimal("Infinity") is None
        assert parse_decimal("-Infinity") is None

    def test_nan_decimal_instance_rejected(self) -> None:
        """A Decimal("NaN") passed directly is rejected, not returned as-is."""
        assert parse_decimal(Decimal("NaN")) is None

    def test_nan_float_rejected(self) -> None:
        """A float('nan') passed directly is rejected."""
        assert parse_decimal(float("nan")) is None

    def test_int_and_float_pass_through(self) -> None:
        """Numeric types convert to an equivalent Decimal."""
        assert parse_decimal(5) == Decimal("5")
        assert parse_decimal(4.5) == Decimal("4.5")


class TestParseInt:
    """Tests for parse_int()."""

    def test_plain_integer(self) -> None:
        """A plain integer string parses normally."""
        assert parse_int("10") == 10

    def test_infinity_returns_none_not_overflow(self) -> None:
        """An Infinity value must not raise OverflowError, just fail to parse."""
        assert parse_int("Infinity") is None
        assert parse_int("-Infinity") is None

    def test_nan_returns_none(self) -> None:
        """A NaN value returns None."""
        assert parse_int("NaN") is None

    def test_blank_returns_none(self) -> None:
        """An empty value returns None."""
        assert parse_int("") is None
