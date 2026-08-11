"""Adapter that reads transaction lines out of another system's database.

This is the pull counterpart to the posting endpoint: instead of the merchant
sending records, the system reads them from a database it is given access to.
No code is written per merchant. A query and a column mapping are enough,
which is what keeps the system reusable across shops whose schemas have
nothing in common.

    configuration = SQLSourceConfiguration(
        url="postgresql+psycopg://reader:secret@shop-db:5432/shop",
        query="SELECT * FROM order_lines WHERE created_at >= :since",
        columns={
            "order_number": "order_reference",
            "ordered_at": "created_at",
            "stock_code": "sku",
            "quantity": "units",
            "unit_price": "price_each",
            "region_name": "shipping_country",
        },
        parameters={"since": "2024-01-01"},
    )

The mapping is deliberately one-directional and explicit. Guessing a merchant's
column names from their spelling works until the day it silently matches the
wrong column, and a wrong mapping is far more expensive than a missing one.
"""

from __future__ import annotations

from typing import TYPE_CHECKING
from typing import Any

from pydantic import BaseModel
from pydantic import Field
from pydantic import field_validator
from sqlalchemy import create_engine
from sqlalchemy import text

from app.core.logging import get_logger
from app.ingestion import normalisation
from app.ingestion.base import CanonicalRecord
from app.ingestion.base import DataSourceAdapter

if TYPE_CHECKING:
    from collections.abc import Iterator

logger = get_logger("ingestion.sql_source")

# Canonical fields a source must supply. Everything else can be absent: a shop
# with no regions, no descriptions or no customer accounts is still analysable,
# just over fewer dimensions.
REQUIRED_FIELDS: tuple[str, ...] = (
    "order_number",
    "ordered_at",
    "stock_code",
    "quantity",
    "unit_price",
)

OPTIONAL_FIELDS: tuple[str, ...] = (
    "description",
    "customer_identifier",
    "region_name",
    "is_cancellation",
)


class SQLSourceConfiguration(BaseModel):
    """Everything needed to read one merchant's transaction lines.

    Attributes:
        url: SQLAlchemy URL of the source database, read-only credentials
        query: Statement returning one row per transaction line
        columns: Canonical field name mapped onto the column that carries it
        parameters: Bound parameters for the query
        cancellation_prefix: Order-number prefix marking a cancelled
            transaction, as many exports encode it that way rather than in a
            column of its own
        non_product_codes: Stock codes to treat as administrative rather than
            merchandise, for example postage or manual adjustments
        batch_size: Rows fetched per round trip
    """

    url: str
    query: str
    columns: dict[str, str]
    parameters: dict[str, Any] = Field(default_factory=dict)
    cancellation_prefix: str | None = None
    non_product_codes: frozenset[str] = frozenset()
    batch_size: int = Field(default=1000, ge=1, le=100_000)

    @field_validator("columns")
    @classmethod
    def validate_columns(cls, value: dict[str, str]) -> dict[str, str]:
        """Reject a mapping that cannot produce a usable record.

        Args:
            value: The supplied canonical-field to column mapping.

        Returns:
            The mapping, unchanged.

        Raises:
            ValueError: If a required field is missing or an unknown field is
                mapped. An unknown field is almost always a typo in a
                canonical name, and silently ignoring it would drop data the
                caller believed they had sent.
        """
        missing = [field for field in REQUIRED_FIELDS if field not in value]
        if missing:
            message = f"columns is missing required fields: {', '.join(missing)}"
            raise ValueError(message)

        known = set(REQUIRED_FIELDS) | set(OPTIONAL_FIELDS)
        unknown = sorted(set(value) - known)
        if unknown:
            message = (
                f"columns maps unknown canonical fields: {', '.join(unknown)}. "
                f"Known fields: {', '.join(sorted(known))}"
            )
            raise ValueError(message)

        return value


class SQLDataSourceAdapter(DataSourceAdapter):
    """Streams canonical transaction lines out of an external database.

    Attributes:
        configuration: Connection, query and column mapping to use
    """

    def __init__(self, configuration: SQLSourceConfiguration) -> None:
        """Initialise the adapter.

        Args:
            configuration: Connection, query and column mapping to use.
        """
        self.configuration = configuration

    def _record_from(self, row: dict[str, Any]) -> CanonicalRecord | str:
        """Build one canonical record from a source row.

        Args:
            row: One result row, keyed by the source's own column names.

        Returns:
            The canonical record, or the reason the row is unusable.
        """
        columns = self.configuration.columns

        def value(field: str) -> Any:  # noqa: ANN401
            column = columns.get(field)
            return None if column is None else row.get(column)

        order_number = normalisation.parse_text(value("order_number")) or ""
        stock_code = normalisation.parse_text(value("stock_code")) or ""
        if not order_number or not stock_code:
            return normalisation.MISSING_IDENTIFIER

        ordered_at = normalisation.parse_datetime(value("ordered_at"))
        if ordered_at is None:
            return normalisation.UNPARSEABLE_DATE

        quantity = normalisation.parse_int(value("quantity"))
        if quantity is None:
            return normalisation.UNPARSEABLE_QUANTITY

        unit_price = normalisation.parse_decimal(value("unit_price"))
        if unit_price is None:
            return normalisation.UNPARSEABLE_PRICE

        prefix = self.configuration.cancellation_prefix
        flagged = normalisation.parse_bool(value("is_cancellation"))
        if prefix:
            flagged = flagged or order_number.upper().startswith(prefix.upper())

        record = CanonicalRecord(
            order_number=order_number,
            ordered_at=ordered_at,
            stock_code=stock_code,
            quantity=quantity,
            unit_price=unit_price,
            description=normalisation.parse_text(value("description")),
            customer_identifier=normalisation.parse_text(value("customer_identifier")),
            region_name=normalisation.parse_text(value("region_name")),
            is_cancellation=flagged,
        )

        reason = normalisation.classify_record(
            record, self.configuration.non_product_codes
        )
        return reason if reason is not None else record

    def fetch(self) -> Iterator[CanonicalRecord]:
        """Yield the source database's usable transaction lines.

        Rows stream in batches rather than being materialised: a merchant's
        order history is the same order of magnitude as a file export.

        Yields:
            One `CanonicalRecord` per usable source row.
        """
        skipped: dict[str, int] = {}
        yielded = 0

        engine = create_engine(self.configuration.url)
        try:
            with engine.connect() as connection:
                result = connection.execution_options(
                    stream_results=True,
                    yield_per=self.configuration.batch_size,
                ).execute(text(self.configuration.query), self.configuration.parameters)

                for row in result.mappings():
                    outcome = self._record_from(dict(row))
                    if isinstance(outcome, str):
                        normalisation.count_skip(skipped, outcome)
                        continue

                    yielded += 1
                    yield outcome
        finally:
            engine.dispose()

        logger.info(
            "sql_source_fetch_complete",
            source=self.source_name,
            yielded=yielded,
            skipped=skipped,
        )

    @property
    def source_name(self) -> str:
        """Provenance label for this source.

        Returns:
            The adapter name with the source database, credentials removed.
        """
        host = self.configuration.url.rsplit("@", maxsplit=1)[-1]
        return f"SQLDataSourceAdapter({host})"
