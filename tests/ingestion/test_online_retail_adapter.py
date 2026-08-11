"""Unit tests for the Online Retail II CSV adapter."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from pathlib import Path

import pytest

from app.ingestion.online_retail import OnlineRetailCSVAdapter

FIXTURE = (
    Path(__file__).resolve().parent.parent / "fixtures" / "online_retail_sample.csv"
)


class TestOnlineRetailCSVAdapter:
    """Tests for OnlineRetailCSVAdapter.fetch()."""

    def test_reads_expected_number_of_usable_rows(self) -> None:
        """Only rows that can support analysis should be yielded.

        Returns:
            None.
        """
        records = list(OnlineRetailCSVAdapter(FIXTURE).fetch())

        # The fixture holds 18 usable lines plus 4 deliberately unusable ones:
        # zero price, zero quantity, unparseable date, and a missing invoice.
        assert len(records) == 18

    def test_parses_a_row_into_canonical_fields(self) -> None:
        """The first row should map onto the canonical fields.

        Returns:
            None.
        """
        first = next(iter(OnlineRetailCSVAdapter(FIXTURE).fetch()))

        assert first.order_number == "536365"
        assert first.stock_code == "85123A"
        assert first.description == "WHITE HANGING HEART T-LIGHT HOLDER"
        assert first.quantity == 6
        assert first.unit_price == Decimal("2.55")
        assert first.ordered_at == datetime(2010, 12, 1, 8, 26)
        assert first.customer_identifier == "17850"
        assert first.region_name == "United Kingdom"
        assert first.is_cancellation is False

    def test_line_total_is_quantity_times_price(self) -> None:
        """line_total should multiply out, keeping the quantity's sign.

        Returns:
            None.
        """
        first = next(iter(OnlineRetailCSVAdapter(FIXTURE).fetch()))

        assert first.line_total == Decimal("15.30")

    def test_flags_cancellation_invoices(self) -> None:
        """Invoices prefixed with C should be flagged as cancellations.

        Returns:
            None.
        """
        records = list(OnlineRetailCSVAdapter(FIXTURE).fetch())

        cancellations = [record for record in records if record.is_cancellation]

        assert len(cancellations) == 2
        assert all(record.quantity < 0 for record in cancellations)
        assert {record.order_number for record in cancellations} == {
            "C536379",
            "C536383",
        }

    def test_keeps_rows_without_a_customer(self) -> None:
        """Anonymous sales should survive, with no customer identifier.

        Returns:
            None.
        """
        records = list(OnlineRetailCSVAdapter(FIXTURE).fetch())

        anonymous = [record for record in records if record.customer_identifier is None]

        assert len(anonymous) == 2
        assert all(record.region_name == "United Kingdom" for record in anonymous)

    def test_drops_non_positive_prices_and_zero_quantities(self) -> None:
        """Adjustment rows should never reach the canonical stream.

        Returns:
            None.
        """
        codes = {
            record.stock_code for record in OnlineRetailCSVAdapter(FIXTURE).fetch()
        }

        assert "BADPRICE" not in codes
        assert "BADQTY" not in codes
        assert "BADDATE" not in codes
        assert "NOINVOICE" not in codes

    def test_accepts_the_alternative_column_spellings(self, tmp_path: Path) -> None:
        """The 2010-2011 sheet's column names should work unchanged.

        Args:
            tmp_path: Temporary directory fixture.

        Returns:
            None.
        """
        source = tmp_path / "legacy.csv"
        source.write_text(
            "InvoiceNo,StockCode,Description,Quantity,InvoiceDate,UnitPrice,"
            "CustomerID,Country\n"
            "536365,85123A,WHITE HANGING HEART,6,2010-12-01 08:26:00,2.55,"
            "17850,United Kingdom\n",
            encoding="utf-8",
        )

        records = list(OnlineRetailCSVAdapter(source, encoding="utf-8").fetch())

        assert len(records) == 1
        assert records[0].order_number == "536365"
        assert records[0].unit_price == Decimal("2.55")

    def test_accepts_day_first_dates(self, tmp_path: Path) -> None:
        """Exports written with day-first dates should parse.

        Args:
            tmp_path: Temporary directory fixture.

        Returns:
            None.
        """
        source = tmp_path / "dayfirst.csv"
        source.write_text(
            "Invoice,StockCode,Quantity,InvoiceDate,Price\n"
            "536365,85123A,6,01/12/2010 08:26,2.55\n",
            encoding="utf-8",
        )

        records = list(OnlineRetailCSVAdapter(source, encoding="utf-8").fetch())

        assert records[0].ordered_at == datetime(2010, 12, 1, 8, 26)

    def test_missing_file_raises(self, tmp_path: Path) -> None:
        """A missing source file should raise rather than yield nothing.

        Args:
            tmp_path: Temporary directory fixture.

        Returns:
            None.
        """
        adapter = OnlineRetailCSVAdapter(tmp_path / "absent.csv")

        with pytest.raises(FileNotFoundError):
            list(adapter.fetch())

    def test_missing_required_columns_raise(self, tmp_path: Path) -> None:
        """A file without the required columns should raise a clear error.

        Args:
            tmp_path: Temporary directory fixture.

        Returns:
            None.
        """
        source = tmp_path / "wrong.csv"
        source.write_text("Foo,Bar\n1,2\n", encoding="utf-8")

        adapter = OnlineRetailCSVAdapter(source, encoding="utf-8")

        with pytest.raises(ValueError, match="missing required columns"):
            list(adapter.fetch())

    def test_source_name_identifies_the_adapter(self) -> None:
        """source_name should name the adapter for provenance and logs.

        Returns:
            None.
        """
        assert OnlineRetailCSVAdapter(FIXTURE).source_name == "OnlineRetailCSVAdapter"


class TestNonProductCodes:
    """Tests for the administrative stock code filter."""

    def test_administrative_codes_are_excluded(self, tmp_path: Path) -> None:
        """Postage, fees and adjustments are not merchandise.

        Args:
            tmp_path: Temporary directory fixture.

        Returns:
            None.
        """
        source = tmp_path / "admin.csv"
        source.write_text(
            "Invoice,StockCode,Description,Quantity,InvoiceDate,Price\n"
            "1,M,Manual,1,2010-12-01 08:00:00,100.00\n"
            "1,DOT,DOTCOM POSTAGE,1,2010-12-01 08:00:00,50.00\n"
            "1,POST,POSTAGE,1,2010-12-01 08:00:00,18.00\n"
            "1,AMAZONFEE,AMAZON FEE,1,2010-12-01 08:00:00,90.00\n"
            "1,BANK CHARGES,Bank Charges,1,2010-12-01 08:00:00,15.00\n"
            "1,gift_0001_20,Gift Voucher,1,2010-12-01 08:00:00,20.00\n"
            "1,85123A,WHITE HANGING HEART,6,2010-12-01 08:00:00,2.55\n",
            encoding="utf-8",
        )

        records = list(OnlineRetailCSVAdapter(source, encoding="utf-8").fetch())

        assert [record.stock_code for record in records] == ["85123A"]

    def test_genuine_alphabetic_codes_survive(self, tmp_path: Path) -> None:
        """The DCGS range is real merchandise despite its letters.

        A pattern-based filter would wrongly discard these, which is why the
        exclusion list is explicit rather than inferred.

        Args:
            tmp_path: Temporary directory fixture.

        Returns:
            None.
        """
        source = tmp_path / "dcgs.csv"
        source.write_text(
            "Invoice,StockCode,Description,Quantity,InvoiceDate,Price\n"
            "1,DCGSSGIRL,GIRLS PARTY BAG,2,2010-12-01 08:00:00,3.36\n"
            "1,DCGS0076,SUNJAR LED NIGHT LIGHT,1,2010-12-01 08:00:00,19.96\n",
            encoding="utf-8",
        )

        records = list(OnlineRetailCSVAdapter(source, encoding="utf-8").fetch())

        assert {record.stock_code for record in records} == {
            "DCGSSGIRL",
            "DCGS0076",
        }

    def test_exclusion_list_can_be_overridden(self, tmp_path: Path) -> None:
        """A different merchant can supply its own codes, or none.

        Args:
            tmp_path: Temporary directory fixture.

        Returns:
            None.
        """
        source = tmp_path / "override.csv"
        source.write_text(
            "Invoice,StockCode,Description,Quantity,InvoiceDate,Price\n"
            "1,M,Manual,1,2010-12-01 08:00:00,100.00\n",
            encoding="utf-8",
        )

        kept = list(
            OnlineRetailCSVAdapter(
                source, encoding="utf-8", non_product_codes=frozenset()
            ).fetch()
        )

        assert [record.stock_code for record in kept] == ["M"]

    def test_matching_is_case_insensitive(self, tmp_path: Path) -> None:
        """Codes appear in mixed case across the two sheets.

        Args:
            tmp_path: Temporary directory fixture.

        Returns:
            None.
        """
        source = tmp_path / "case.csv"
        source.write_text(
            "Invoice,StockCode,Description,Quantity,InvoiceDate,Price\n"
            "1,m,Manual,1,2010-12-01 08:00:00,100.00\n"
            "1,Post,POSTAGE,1,2010-12-01 08:00:00,18.00\n",
            encoding="utf-8",
        )

        assert list(OnlineRetailCSVAdapter(source, encoding="utf-8").fetch()) == []
