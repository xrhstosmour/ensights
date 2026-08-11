"""Response schemas for the business metrics endpoints."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from pydantic import Field

from app.schemas.base import BaseSchema


class GrossMerchandiseValueRow(BaseSchema):
    """Merchandise value within one calendar bucket."""

    period: datetime
    orders: int = 0
    gross_merchandise_value: Decimal = Decimal("0")
    refunds: Decimal = Decimal("0")
    net_merchandise_value: Decimal = Decimal("0")


class CustomerSummary(BaseSchema):
    """Headline customer counts and the repeat purchase rate."""

    customers: int = 0
    repeat_customers: int = 0
    one_time_customers: int = 0
    repeat_purchase_rate: float = Field(
        default=0.0,
        description="Share of identified customers with more than one order.",
    )
    average_orders_per_customer: float = 0.0
    average_order_value: float = 0.0


class CohortRetentionRow(BaseSchema):
    """One cell of the acquisition-cohort retention grid."""

    cohort_month: datetime
    period_index: int = Field(
        description="Whole months after acquisition; 0 is the cohort's own month."
    )
    active_customers: int = 0
    cohort_size: int = 0
    retention_rate: float = 0.0


class RfmRow(BaseSchema):
    """Recency, frequency and monetary value for one customer."""

    customer_identifier: str
    region: str | None = None
    recency_days: int = 0
    frequency: int = 0
    monetary: Decimal = Field(
        default=Decimal("0"),
        description=(
            "Observed value to date. This is not a predicted lifetime value, "
            "no model is involved."
        ),
    )
    first_purchase: datetime | None = None
    last_purchase: datetime | None = None
