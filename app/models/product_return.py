"""Product return model for the canonical e-commerce schema.

Named `ProductReturn` rather than `Return` so the class never shadows the
`return` keyword in readers' minds; the table is `returns`.
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy import Index
from sqlmodel import Field

from app.models.base import BaseModel


class ProductReturn(BaseModel, table=True):
    """A refunded or cancelled sale line.

    Returns are modelled as their own rows rather than negative order lines so
    that refund analysis never has to be netted out of revenue by accident.
    `quantity` and `amount` are stored positive, the direction is implied by
    the entity.

    `original_order_id` is nullable because sources commonly report a
    cancellation without a reliable pointer back to the sale it reverses. Where
    that link cannot be established, the return still counts towards
    product-level refund rates.

    Attributes:
        id: UUID primary key
        product_id: Product that was returned
        customer_id: Buyer who returned it, when known
        region_id: Region the return happened in
        original_order_id: Sale being reversed, when it can be resolved
        return_order_number: The cancellation's identifier in the source system
        quantity: Units returned, stored positive
        amount: Value refunded, stored positive
        returned_at: When the return took place
        tenant_id: Organization that owns this record
        created_at: When the record was created
        updated_at: When the record was last modified
        deleted_at: Soft delete timestamp
    """

    __tablename__ = "returns"  # pyright: ignore[reportAssignmentType]
    # "Which products do I get the most refunds on" groups by product, and the
    # refund time series filters by date.
    __table_args__ = (
        Index("ix_returns_tenant_id_product_id", "tenant_id", "product_id"),
        Index("ix_returns_tenant_id_returned_at", "tenant_id", "returned_at"),
    )

    product_id: UUID = Field(
        foreign_key="products.id",
        nullable=False,
        index=True,
    )

    customer_id: UUID | None = Field(
        default=None,
        foreign_key="customers.id",
        nullable=True,
        index=True,
    )

    region_id: UUID | None = Field(
        default=None,
        foreign_key="regions.id",
        nullable=True,
        index=True,
    )

    original_order_id: UUID | None = Field(
        default=None,
        foreign_key="orders.id",
        nullable=True,
        index=True,
    )

    return_order_number: str = Field(
        nullable=False,
        index=True,
        max_length=64,
    )

    quantity: int = Field(
        nullable=False,
    )

    amount: Decimal = Field(
        nullable=False,
        max_digits=14,
        decimal_places=4,
    )

    returned_at: datetime = Field(
        nullable=False,
        index=True,
    )
