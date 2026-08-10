"""Customer model for the canonical e-commerce schema.

A customer here is the buying party as the source system reports it, keyed by
`external_identifier` so repeated imports are idempotent. This is deliberately
not the `User` model: `User` authenticates against this application, a
`Customer` is a record of someone who bought from the analysed store.
"""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import Index
from sqlmodel import Field

from app.models.base import BaseModel


class Customer(BaseModel, table=True):
    """A buyer in the analysed store.

    Attributes:
        id: UUID primary key
        external_identifier: The buyer's identifier in the source system
        region_id: Region the buyer is associated with
        tenant_id: Organization that owns this record
        created_at: When the record was created
        updated_at: When the record was last modified
        deleted_at: Soft delete timestamp
    """

    __tablename__ = "customers"  # pyright: ignore[reportAssignmentType]
    # Import resolves customers by (tenant, external identifier) on every row,
    # and the region breakdown groups by region.
    __table_args__ = (
        Index(
            "ix_customers_tenant_id_external_identifier",
            "tenant_id",
            "external_identifier",
        ),
        Index("ix_customers_tenant_id_region_id", "tenant_id", "region_id"),
    )

    external_identifier: str = Field(
        nullable=False,
        index=True,
        max_length=128,
    )

    region_id: UUID | None = Field(
        default=None,
        foreign_key="regions.id",
        nullable=True,
        index=True,
    )
