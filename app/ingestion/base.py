"""Source-agnostic ingestion contract.

A source is anything that can produce transaction lines: a CSV export, another
application's database, a shop platform's API. Each one implements
`DataSourceAdapter` and yields `CanonicalRecord` values; everything downstream
of that point is written against the canonical schema alone.
"""

from __future__ import annotations

from abc import ABC
from abc import abstractmethod
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Iterator


@dataclass(frozen=True, slots=True)
class CanonicalRecord:
    """One transaction line, normalised across sources.

    This is deliberately flat and denormalised: it mirrors how transactional
    exports actually look, one row per product sold within a transaction. The
    ingestion service is what turns a stream of these into the related
    entities.

    A negative `quantity` means the line reverses a sale. Adapters pass the
    source's sign through unchanged rather than deciding what it means; the
    ingestion service owns that interpretation so every source is treated
    identically.

    Attributes:
        order_number: Transaction identifier in the source system
        ordered_at: When the transaction took place
        stock_code: Product identifier in the source system
        quantity: Units, negative when the line reverses a sale
        unit_price: Price per unit charged on this line
        description: Free-text product description, when the source has one
        customer_identifier: Buyer identifier, None for anonymous sales
        region_name: Region the sale happened in, when the source has one
        is_cancellation: Whether the source flags the whole transaction as
            cancelled, independently of the quantity sign
    """

    order_number: str
    ordered_at: datetime
    stock_code: str
    quantity: int
    unit_price: Decimal
    description: str | None = None
    customer_identifier: str | None = None
    region_name: str | None = None
    is_cancellation: bool = False

    @property
    def line_total(self) -> Decimal:
        """Value of this line, signed the same way as `quantity`.

        Returns:
            `quantity` multiplied by `unit_price`.
        """
        return Decimal(self.quantity) * self.unit_price


class DataSourceAdapter(ABC):
    """Base class for anything that can produce canonical transaction lines.

    Implementations stream rather than materialise. Real exports run to
    millions of rows, and the ingestion service batches on its own terms.
    """

    @abstractmethod
    def fetch(self) -> Iterator[CanonicalRecord]:
        """Yield the source's transaction lines in canonical form.

        Yields:
            One `CanonicalRecord` per usable source row.

        Raises:
            ValueError: If the source is structurally unusable, for example a
                CSV whose required columns cannot be identified.
        """
        raise NotImplementedError

    @property
    def source_name(self) -> str:
        """Human-readable name for logs and provenance.

        Returns:
            The adapter's class name by default.
        """
        return type(self).__name__
