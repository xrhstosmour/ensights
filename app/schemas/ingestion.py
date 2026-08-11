"""Public request and response schemas for pushing transaction data.

These schemas are the published form of the canonical contract described in
`documents/ingestion-contract.md`. A merchant who can produce this shape can
be analysed by the system without a line of code being written for them, which
is what the generality requirement of the thesis amounts to in practice.
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from pydantic import Field

from app.ingestion.base import CanonicalRecord
from app.schemas.base import BaseSchema

# Batches are bounded so one request cannot hold a worker for an unbounded
# time. Larger histories are sent as several requests, or pulled straight from
# the merchant's database instead.
MAXIMUM_BATCH_SIZE = 5_000


class TransactionLineIn(BaseSchema):
    """One transaction line in canonical form.

    A line is one product within one transaction, which is how transactional
    exports are actually shaped. Reversals are sent exactly as the source
    records them: a negative quantity, a cancellation flag, or both. The
    system decides what that means, so that every source is interpreted
    identically.
    """

    order_number: str = Field(
        min_length=1,
        max_length=64,
        description="Transaction identifier in the merchant's own system.",
    )
    ordered_at: datetime = Field(description="When the transaction took place.")
    stock_code: str = Field(
        min_length=1,
        max_length=64,
        description="Product identifier in the merchant's own system.",
    )
    quantity: int = Field(
        description="Units on this line, negative when the line reverses a sale."
    )
    unit_price: Decimal = Field(
        description="Price per unit as actually charged on this line."
    )
    description: str | None = Field(
        default=None, max_length=512, description="Free-text product description."
    )
    customer_identifier: str | None = Field(
        default=None,
        max_length=64,
        description="Buyer identifier. Omit for anonymous sales, which stay in "
        "product, region and time analyses and are excluded only from "
        "customer-level ones.",
    )
    region_name: str | None = Field(
        default=None,
        max_length=128,
        description="Region the sale happened in, at whatever granularity the "
        "merchant records: country, state or city.",
    )
    is_cancellation: bool = Field(
        default=False,
        description="Whether the merchant flags the whole transaction as "
        "cancelled, independently of the quantity sign.",
    )

    def to_canonical(self) -> CanonicalRecord:
        """Convert to the internal canonical record.

        Returns:
            The equivalent `CanonicalRecord`.
        """
        return CanonicalRecord(
            order_number=self.order_number.strip(),
            ordered_at=self.ordered_at,
            stock_code=self.stock_code.strip(),
            quantity=self.quantity,
            unit_price=self.unit_price,
            description=self.description,
            customer_identifier=self.customer_identifier,
            region_name=self.region_name,
            is_cancellation=self.is_cancellation,
        )


class TransactionBatchIn(BaseSchema):
    """A batch of transaction lines submitted by a merchant."""

    source_name: str = Field(
        default="posted-batch",
        max_length=128,
        description="Where the batch came from, recorded for provenance.",
    )
    records: list[TransactionLineIn] = Field(
        min_length=1,
        max_length=MAXIMUM_BATCH_SIZE,
        description="The transaction lines to import.",
    )
    non_product_codes: list[str] = Field(
        default_factory=list,
        description="Stock codes the merchant treats as administrative rather "
        "than merchandise, for example postage or manual adjustments. They are "
        "rejected instead of imported, because left in they dominate every "
        "revenue ranking.",
    )


class RejectedLine(BaseSchema):
    """One submitted line that could not be imported."""

    index: int = Field(description="Position of the line in the submitted batch.")
    order_number: str = Field(description="Transaction identifier of the line.")
    reason: str = Field(description="Why the line cannot support analysis.")


class ImportResult(BaseSchema):
    """Outcome of one import run.

    Rejections are reported per line rather than aggregated away. A caller who
    sent a thousand lines and had four dropped is entitled to know which four,
    otherwise the only way to find out is to compare totals.
    """

    source_name: str = Field(description="Where the imported lines came from.")
    records_received: int = Field(description="Lines submitted.")
    records_accepted: int = Field(description="Lines that passed the rules.")
    orders_created: int = Field(description="Sale transactions inserted.")
    order_items_created: int = Field(description="Sale lines inserted.")
    returns_created: int = Field(description="Return lines inserted.")
    transactions_skipped: int = Field(
        description="Transactions already present, left untouched."
    )
    customers_created: int = Field(description="New buyers registered.")
    products_created: int = Field(description="New products registered.")
    regions_created: int = Field(description="New regions registered.")
    rejected: list[RejectedLine] = Field(
        default_factory=list, description="Lines that could not be imported."
    )
