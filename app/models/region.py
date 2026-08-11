"""Region model for geographic grouping of sales.

Regions are deliberately coarse. The canonical schema keeps a single level so
that any source, whether it reports a country, a state, or a city, maps onto
the same entity. Finer granularity can be added later as a self-referencing
parent without touching the analytics layer.
"""

from __future__ import annotations

from sqlalchemy import Index
from sqlmodel import Field

from app.models.base import BaseModel


class Region(BaseModel, table=True):
    """Geographic region a customer or order belongs to.

    Attributes:
        id: UUID primary key
        name: Human-readable region name, for example "United Kingdom"
        code: Optional short code, for example an ISO country code
        tenant_id: Organization that owns this record
        created_at: When the record was created
        updated_at: When the record was last modified
        deleted_at: Soft delete timestamp
    """

    __tablename__ = "regions"  # pyright: ignore[reportAssignmentType]
    # Regions are resolved by name during import, once per row, so the lookup
    # is scoped to the tenant and indexed.
    __table_args__ = (Index("ix_regions_tenant_id_name", "tenant_id", "name"),)

    name: str = Field(
        nullable=False,
        index=True,
        max_length=255,
    )

    code: str | None = Field(
        default=None,
        nullable=True,
        max_length=16,
    )
