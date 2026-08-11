"""Unit tests for the configuration-driven SQL source adapter.

The source here is SQLite, deliberately: it shares no schema, no column names
and no engine with the CSV export the rest of the thesis runs on, so a passing
test is evidence that the pipeline is genuinely source-agnostic rather than
merely written as if it were.
"""

from __future__ import annotations

import sqlite3
from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING

import pytest
from pydantic import ValidationError

from app.ingestion.sql_source import SQLDataSourceAdapter
from app.ingestion.sql_source import SQLSourceConfiguration

if TYPE_CHECKING:
    from pathlib import Path

# A shop schema that has nothing in common with the Online Retail II columns.
SCHEMA = """
CREATE TABLE order_lines (
    order_reference TEXT,
    created_at TEXT,
    sku TEXT,
    units INTEGER,
    price_each REAL,
    product_title TEXT,
    buyer TEXT,
    shipping_country TEXT
)
"""

ROWS = [
    ("SO-1", "2024-01-15 10:30:00", "TEA-01", 3, 4.5, "Green tea", "b-1", "Greece"),
    ("SO-1", "2024-01-15 10:30:00", "MUG-02", 1, 12.0, "Mug", "b-1", "Greece"),
    ("SO-2", "2024-01-16 09:00:00", "TEA-01", 2, 4.5, "Green tea", None, "Cyprus"),
    # Reversal: the shop records it as a negative quantity.
    ("SO-3", "2024-01-20 11:00:00", "MUG-02", -1, 12.0, "Mug", "b-1", "Greece"),
    # Unusable: a zero price is an adjustment rather than trade.
    ("SO-4", "2024-01-21 11:00:00", "MUG-02", 1, 0.0, "Mug", "b-2", "Greece"),
    # Unusable: no product identifier to attribute the line to.
    ("SO-5", "2024-01-22 11:00:00", None, 1, 5.0, "Mystery", "b-2", "Greece"),
    # Administrative rather than merchandise, when configured as such.
    ("SO-6", "2024-01-23 11:00:00", "POSTAGE", 1, 6.0, "Postage", "b-1", "Greece"),
]

COLUMNS = {
    "order_number": "order_reference",
    "ordered_at": "created_at",
    "stock_code": "sku",
    "quantity": "units",
    "unit_price": "price_each",
    "description": "product_title",
    "customer_identifier": "buyer",
    "region_name": "shipping_country",
}


@pytest.fixture(name="shop_database")
def shop_database_fixture(tmp_path: Path) -> str:
    """Create a throwaway shop database with its own schema.

    Args:
        tmp_path: Temporary directory provided by pytest.

    Returns:
        SQLAlchemy URL of the created database.
    """
    path = tmp_path / "shop.sqlite"
    connection = sqlite3.connect(path)
    try:
        connection.execute(SCHEMA)
        connection.executemany(
            "INSERT INTO order_lines VALUES (?, ?, ?, ?, ?, ?, ?, ?)", ROWS
        )
        connection.commit()
    finally:
        connection.close()

    return f"sqlite:///{path}"


class TestSQLSourceConfiguration:
    """Tests for the source configuration's own validation."""

    def test_rejects_a_mapping_missing_a_required_field(self) -> None:
        """A mapping without every required field cannot produce a record.

        Returns:
            None.
        """
        columns = {key: value for key, value in COLUMNS.items() if key != "unit_price"}

        with pytest.raises(ValidationError, match="unit_price"):
            SQLSourceConfiguration(url="sqlite://", query="SELECT 1", columns=columns)

    def test_rejects_an_unknown_canonical_field(self) -> None:
        """A misspelled canonical name must fail rather than be ignored.

        Returns:
            None.
        """
        columns = COLUMNS | {"unit_prices": "price_each"}

        with pytest.raises(ValidationError, match="unit_prices"):
            SQLSourceConfiguration(url="sqlite://", query="SELECT 1", columns=columns)


class TestSQLDataSourceAdapter:
    """Tests for SQLDataSourceAdapter.fetch()."""

    def _configuration(self, url: str, **overrides: object) -> SQLSourceConfiguration:
        """Build a configuration against the throwaway shop database.

        Args:
            url: SQLAlchemy URL of the shop database.
            **overrides: Fields to override on the configuration.

        Returns:
            The configuration to hand to the adapter.
        """
        fields: dict[str, object] = {
            "url": url,
            "query": "SELECT * FROM order_lines ORDER BY order_reference",
            "columns": COLUMNS,
        }
        fields.update(overrides)
        return SQLSourceConfiguration(**fields)  # type: ignore[arg-type]

    def test_reads_only_usable_rows(self, shop_database: str) -> None:
        """Rows that cannot support analysis should not be yielded.

        Args:
            shop_database: URL of the throwaway shop database.

        Returns:
            None.
        """
        adapter = SQLDataSourceAdapter(self._configuration(shop_database))

        records = list(adapter.fetch())

        # Seven rows in, two rejected: the zero price and the missing SKU.
        assert len(records) == 5

    def test_maps_a_foreign_schema_onto_canonical_fields(
        self, shop_database: str
    ) -> None:
        """A shop's own column names should arrive as canonical fields.

        Args:
            shop_database: URL of the throwaway shop database.

        Returns:
            None.
        """
        adapter = SQLDataSourceAdapter(self._configuration(shop_database))

        first = next(iter(adapter.fetch()))

        assert first.order_number == "SO-1"
        assert first.ordered_at == datetime(2024, 1, 15, 10, 30)
        assert first.stock_code == "TEA-01"
        assert first.quantity == 3
        assert first.unit_price == Decimal("4.5")
        assert first.description == "Green tea"
        assert first.customer_identifier == "b-1"
        assert first.region_name == "Greece"
        assert first.is_cancellation is False

    def test_passes_reversals_through_untouched(self, shop_database: str) -> None:
        """A negative quantity keeps its sign for the service to interpret.

        Args:
            shop_database: URL of the throwaway shop database.

        Returns:
            None.
        """
        records = list(SQLDataSourceAdapter(self._configuration(shop_database)).fetch())

        reversal = next(record for record in records if record.order_number == "SO-3")

        assert reversal.quantity == -1

    def test_applies_the_configured_cancellation_prefix(
        self, shop_database: str
    ) -> None:
        """A shop encoding cancellations in the reference should be honoured.

        Args:
            shop_database: URL of the throwaway shop database.

        Returns:
            None.
        """
        configuration = self._configuration(shop_database, cancellation_prefix="SO-3")
        records = list(SQLDataSourceAdapter(configuration).fetch())

        flagged = [record for record in records if record.is_cancellation]

        assert [record.order_number for record in flagged] == ["SO-3"]

    def test_rejects_configured_administrative_codes(self, shop_database: str) -> None:
        """Postage and the like should be dropped when the shop names them.

        Args:
            shop_database: URL of the throwaway shop database.

        Returns:
            None.
        """
        configuration = self._configuration(
            shop_database, non_product_codes=frozenset({"POSTAGE"})
        )

        records = list(SQLDataSourceAdapter(configuration).fetch())

        assert all(record.stock_code != "POSTAGE" for record in records)
        assert len(records) == 4

    def test_binds_query_parameters(self, shop_database: str) -> None:
        """A parameterised query should receive its bound values.

        Args:
            shop_database: URL of the throwaway shop database.

        Returns:
            None.
        """
        configuration = self._configuration(
            shop_database,
            query="SELECT * FROM order_lines WHERE created_at >= :since",
            parameters={"since": "2024-01-20"},
        )

        records = list(SQLDataSourceAdapter(configuration).fetch())

        assert {record.order_number for record in records} == {"SO-3", "SO-6"}

    def test_source_name_hides_credentials(self) -> None:
        """Provenance must not leak the password out of the URL.

        Returns:
            None.
        """
        configuration = SQLSourceConfiguration(
            url="postgresql+psycopg://reader:secret@shop-db:5432/shop",
            query="SELECT 1",
            columns=COLUMNS,
        )

        name = SQLDataSourceAdapter(configuration).source_name

        assert "secret" not in name
        assert "shop-db:5432/shop" in name
