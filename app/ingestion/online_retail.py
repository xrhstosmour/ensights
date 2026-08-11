"""Adapter for the UCI Online Retail II dataset.

The dataset ships as two sheets covering 2009-2010 and 2010-2011, and the two
do not agree on column names: the earlier one uses `Invoice`, `Price` and
`Customer ID`, the later one `InvoiceNo`, `UnitPrice` and `CustomerID`. Both
spellings are accepted here so either export, or a CSV conversion of either,
works untouched.

Reference: Chen, D., Sain, S. L. and Guo, K. (2012), "Data mining for the
online retail industry".
"""

from __future__ import annotations

import csv
from pathlib import Path
from typing import TYPE_CHECKING

from app.core.logging import get_logger
from app.ingestion import normalisation
from app.ingestion.base import CanonicalRecord
from app.ingestion.base import DataSourceAdapter

if TYPE_CHECKING:
    from collections.abc import Iterator

logger = get_logger("ingestion.online_retail")

# Accepted spellings per canonical field, lowercased for comparison.
_COLUMN_ALIASES: dict[str, tuple[str, ...]] = {
    "order_number": ("invoice", "invoiceno"),
    "stock_code": ("stockcode",),
    "description": ("description",),
    "quantity": ("quantity",),
    "ordered_at": ("invoicedate",),
    "unit_price": ("price", "unitprice"),
    "customer_identifier": ("customer id", "customerid"),
    "region_name": ("country",),
}

# Stock codes that are not products.
#
# The dataset records postage, manual adjustments, fees, samples, discounts and
# at least one test row through the same line format as real merchandise. Left
# in, they dominate the results: "Manual" and "DOTCOM POSTAGE" rank first and
# third by revenue, and "Manual" alone accounts for more refunded value than
# any genuine product.
#
# They cannot be filtered by pattern. Some are numeric-looking and some real
# products carry alphabetic codes (the DCGS range is genuine merchandise), so
# the list is explicit. Gift vouchers are excluded too: they are a payment
# instrument, and counting both the voucher and the goods it buys is double
# counting.
#
# Pass `non_product_codes` to override this for a different merchant.
NON_PRODUCT_STOCK_CODES = frozenset(
    {
        "ADJUST",
        "ADJUST2",
        "AMAZONFEE",
        "B",
        "BANK CHARGES",
        "C2",
        "CRUK",
        "D",
        "DOT",
        "M",
        "PADS",
        "POST",
        "S",
        "TEST001",
        "TEST002",
    }
)

_REQUIRED_FIELDS = (
    "order_number",
    "stock_code",
    "quantity",
    "ordered_at",
    "unit_price",
)


class OnlineRetailCSVAdapter(DataSourceAdapter):
    """Streams Online Retail II transaction lines from a CSV file.

    Rows are skipped, with a counted reason, when they cannot support any
    analysis: an unparseable date or quantity, a missing product code, a
    non-positive price, or a zero quantity. Non-positive prices are dropped
    because the dataset uses them for stock adjustments and bad-debt entries
    rather than trade, and including them distorts every revenue figure.

    Rows with no customer identifier are kept. Roughly a quarter of the
    dataset has none, and they are still real sales that belong in product,
    region and time analyses; only the customer-level analyses exclude them.

    Attributes:
        path: Location of the CSV file to read
        encoding: File encoding, the published exports are Latin-1
    """

    def __init__(
        self,
        path: Path | str,
        encoding: str = "latin-1",
        non_product_codes: frozenset[str] | None = None,
    ) -> None:
        """Initialise the adapter.

        Args:
            path: Location of the CSV file to read.
            encoding: File encoding, defaults to the published exports' Latin-1.
            non_product_codes: Stock codes to treat as administrative rather
                than merchandise. Defaults to `NON_PRODUCT_STOCK_CODES`; pass
                an empty set to keep everything.
        """
        self.path = Path(path)
        self.encoding = encoding
        self.non_product_codes = (
            NON_PRODUCT_STOCK_CODES if non_product_codes is None else non_product_codes
        )

    def _resolve_columns(self, header: list[str]) -> dict[str, str]:
        """Map canonical field names onto this file's actual column names.

        Args:
            header: Column names as they appear in the file.

        Returns:
            Mapping of canonical field name to the file's column name.

        Raises:
            ValueError: If a required column cannot be identified.
        """
        normalised = {name.strip().lower(): name for name in header}
        resolved: dict[str, str] = {}

        for field, aliases in _COLUMN_ALIASES.items():
            for alias in aliases:
                if alias in normalised:
                    resolved[field] = normalised[alias]
                    break

        missing = [field for field in _REQUIRED_FIELDS if field not in resolved]
        if missing:
            message = (
                f"{self.path} is missing required columns: {', '.join(missing)}. "
                f"Found: {', '.join(header)}"
            )
            raise ValueError(message)

        return resolved

    def fetch(self) -> Iterator[CanonicalRecord]:
        """Yield the file's usable transaction lines.

        Yields:
            One `CanonicalRecord` per usable row.

        Raises:
            FileNotFoundError: If the configured path does not exist.
            ValueError: If required columns cannot be identified.
        """
        if not self.path.exists():
            message = f"Source file not found: {self.path}"
            raise FileNotFoundError(message)

        skipped: dict[str, int] = {}
        yielded = 0

        def skip(reason: str) -> None:
            skipped[reason] = skipped.get(reason, 0) + 1

        with self.path.open(encoding=self.encoding, newline="") as handle:
            reader = csv.DictReader(handle)
            if reader.fieldnames is None:
                message = f"{self.path} has no header row"
                raise ValueError(message)

            columns = self._resolve_columns(list(reader.fieldnames))

            def value(row: dict[str, str], field: str) -> str:
                column = columns.get(field)
                if column is None:
                    return ""
                return (row.get(column) or "").strip()

            for row in reader:
                order_number = value(row, "order_number")
                stock_code = value(row, "stock_code")
                if not order_number or not stock_code:
                    skip(normalisation.MISSING_IDENTIFIER)
                    continue

                ordered_at = normalisation.parse_datetime(value(row, "ordered_at"))
                if ordered_at is None:
                    skip(normalisation.UNPARSEABLE_DATE)
                    continue

                quantity = normalisation.parse_int(value(row, "quantity"))
                if quantity is None:
                    skip(normalisation.UNPARSEABLE_QUANTITY)
                    continue

                unit_price = normalisation.parse_decimal(value(row, "unit_price"))
                if unit_price is None:
                    skip(normalisation.UNPARSEABLE_PRICE)
                    continue

                record = CanonicalRecord(
                    order_number=order_number,
                    ordered_at=ordered_at,
                    stock_code=stock_code,
                    quantity=quantity,
                    unit_price=unit_price,
                    description=value(row, "description") or None,
                    customer_identifier=value(row, "customer_identifier") or None,
                    region_name=value(row, "region_name") or None,
                    # The dataset marks cancellations with a "C" prefix on the
                    # invoice number, alongside a negative quantity.
                    is_cancellation=order_number.upper().startswith("C"),
                )

                # The remaining rules are shared with every other source, so a
                # posted batch and a CSV export are judged identically.
                reason = normalisation.classify_record(record, self.non_product_codes)
                if reason is not None:
                    skip(reason)
                    continue

                yielded += 1
                yield record

        logger.info(
            "online_retail_fetch_complete",
            path=str(self.path),
            yielded=yielded,
            skipped=skipped,
        )
