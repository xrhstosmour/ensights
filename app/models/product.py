"""Product model for the canonical e-commerce schema."""

from __future__ import annotations

from decimal import Decimal

from sqlalchemy import Index
from sqlmodel import Field

from app.models.base import BaseModel


class Product(BaseModel, table=True):
    """A sellable item in the analysed store.

    `last_unit_price` is a convenience for price-band reporting only. The price
    actually charged is stored per line on `OrderItem`, because the same
    product is frequently sold at different prices over time, and any analysis
    of revenue must use the line price rather than this field.

    Attributes:
        id: UUID primary key
        stock_code: The product's identifier in the source system
        description: Free-text product description from the source
        last_unit_price: Most recently seen unit price, for price banding
        tenant_id: Organization that owns this record
        created_at: When the record was created
        updated_at: When the record was last modified
        deleted_at: Soft delete timestamp
    """

    __tablename__ = "products"  # pyright: ignore[reportAssignmentType]
    # Import resolves products by (tenant, stock code) on every row.
    __table_args__ = (
        Index("ix_products_tenant_id_stock_code", "tenant_id", "stock_code"),
    )

    stock_code: str = Field(
        nullable=False,
        index=True,
        max_length=64,
    )

    description: str | None = Field(
        default=None,
        nullable=True,
        max_length=512,
    )

    last_unit_price: Decimal | None = Field(
        default=None,
        nullable=True,
        max_digits=12,
        decimal_places=4,
    )
