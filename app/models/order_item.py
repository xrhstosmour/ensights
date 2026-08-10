"""Order line item model for the canonical e-commerce schema."""

from __future__ import annotations

from decimal import Decimal
from uuid import UUID

from sqlalchemy import Index
from sqlmodel import Field

from app.models.base import BaseModel


class OrderItem(BaseModel, table=True):
    """One product line within an order.

    `line_total` is stored rather than derived so that revenue aggregates stay
    exact and index-friendly. It is computed once at import as
    `quantity * unit_price`, using the price actually charged on this line.

    Attributes:
        id: UUID primary key
        order_id: Order this line belongs to
        product_id: Product sold on this line
        quantity: Units sold
        unit_price: Price per unit actually charged on this line
        line_total: quantity multiplied by unit_price
        tenant_id: Organization that owns this record
        created_at: When the record was created
        updated_at: When the record was last modified
        deleted_at: Soft delete timestamp
    """

    __tablename__ = "order_items"  # pyright: ignore[reportAssignmentType]
    # Basket construction for frequent itemset mining reads lines by order,
    # and the top-products breakdown groups by product.
    __table_args__ = (
        Index("ix_order_items_tenant_id_order_id", "tenant_id", "order_id"),
        Index("ix_order_items_tenant_id_product_id", "tenant_id", "product_id"),
    )

    order_id: UUID = Field(
        foreign_key="orders.id",
        nullable=False,
        index=True,
    )

    product_id: UUID = Field(
        foreign_key="products.id",
        nullable=False,
        index=True,
    )

    quantity: int = Field(
        nullable=False,
    )

    unit_price: Decimal = Field(
        nullable=False,
        max_digits=12,
        decimal_places=4,
    )

    line_total: Decimal = Field(
        nullable=False,
        max_digits=14,
        decimal_places=4,
    )
