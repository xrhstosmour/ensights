"""Unit tests for shared ingestion parsing rules."""

from __future__ import annotations

from datetime import UTC
from datetime import datetime
from decimal import Decimal

from app.ingestion.base import CanonicalRecord
from app.ingestion.normalisation import classify_record
from app.ingestion.normalisation import parse_bool
from app.ingestion.normalisation import parse_decimal
from app.ingestion.normalisation import parse_int


def _record(stock_code: str) -> CanonicalRecord:
    """Build a minimal valid record for classification tests.

    Args:
        stock_code: The stock code to classify.

    Returns:
        A record that would otherwise pass every check.
    """
    return CanonicalRecord(
        order_number="SO-1",
        ordered_at=datetime(2024, 1, 1, tzinfo=UTC),
        stock_code=stock_code,
        quantity=1,
        unit_price=Decimal("1.00"),
    )


class TestClassifyRecord:
    """Tests for classify_record()."""

    def test_only_caller_supplied_codes_are_rejected(self) -> None:
        """A code not in `non_product_codes` is accepted, whatever it looks like.

        This is the shared function every ingestion source calls, so it must
        not guess at administrative codes on its own; each source declares
        its own. A source-specific quirk, like the Online Retail II adapter's
        gift-voucher prefix, belongs in that adapter, not here.
        """
        assert classify_record(_record("GIFT_0001_20")) is None

    def test_caller_supplied_code_is_rejected(self) -> None:
        """A code declared by the caller is still rejected."""
        reason = classify_record(_record("POSTAGE"), frozenset({"POSTAGE"}))
        assert reason == "non_product_code"


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


class TestParseBool:
    """Tests for parse_bool()."""

    def test_falsy_text_is_false(self) -> None:
        """A "N"/"false"-shaped value must not be Python-truthy-True."""
        assert parse_bool("N") is False
        assert parse_bool("n") is False
        assert parse_bool("false") is False
        assert parse_bool("0") is False
        assert parse_bool("no") is False

    def test_truthy_text_is_true(self) -> None:
        """Common truthy representations are recognized."""
        assert parse_bool("Y") is True
        assert parse_bool("y") is True
        assert parse_bool("true") is True
        assert parse_bool("1") is True
        assert parse_bool("yes") is True

    def test_none_is_false(self) -> None:
        """A missing column value means "not flagged"."""
        assert parse_bool(None) is False

    def test_native_bool_passes_through(self) -> None:
        """A native bool value is returned as-is."""
        assert parse_bool(True) is True
        assert parse_bool(False) is False

    def test_unrecognized_text_is_false(self) -> None:
        """Unrecognized text defaults to False rather than guessing True."""
        assert parse_bool("maybe") is False
