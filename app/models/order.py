"""Order model for the canonical e-commerce schema."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy import Index
from sqlmodel import Field

from app.models.base import BaseModel


class Order(BaseModel, table=True):
    """A single purchase transaction.

    `region_id` is denormalised from the customer on purpose. The region a
    sale happened in is a property of that sale, and copying it here keeps the
    region and time breakdowns, which are the most frequent queries in this
    project, off a customer join. It also stays correct if a customer's region
    is later corrected.

    Attributes:
        id: UUID primary key
        order_number: The transaction identifier in the source system
        customer_id: Buyer, null when the source reports an anonymous sale
        region_id: Region the sale happened in
        ordered_at: When the transaction took place
        is_cancelled: Whether the source marked the whole transaction cancelled
        tenant_id: Organization that owns this record
        created_at: When the record was created
        updated_at: When the record was last modified
        deleted_at: Soft delete timestamp
    """

    __tablename__ = "orders"  # pyright: ignore[reportAssignmentType]
    # The three access paths that matter: idempotent import by order number,
    # the time series, and the region-by-time breakdown that level one
    # clustering builds on.
    __table_args__ = (
        Index("ix_orders_tenant_id_order_number", "tenant_id", "order_number"),
        Index("ix_orders_tenant_id_ordered_at", "tenant_id", "ordered_at"),
        Index(
            "ix_orders_tenant_id_region_id_ordered_at",
            "tenant_id",
            "region_id",
            "ordered_at",
        ),
    )

    order_number: str = Field(
        nullable=False,
        index=True,
        max_length=64,
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

    ordered_at: datetime = Field(
        nullable=False,
        index=True,
    )

    is_cancelled: bool = Field(
        default=False,
        nullable=False,
    )
