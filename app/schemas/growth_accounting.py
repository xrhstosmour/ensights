"""Response schemas for the growth accounting endpoint."""

from __future__ import annotations

from datetime import datetime

from pydantic import Field

from app.schemas.base import BaseSchema


class PeriodFlowsRow(BaseSchema):
    """Revenue decomposition for one period."""

    period: datetime
    revenue: float = 0.0
    previous_revenue: float = 0.0
    new: float = Field(default=0.0, description="Revenue from first-time customers.")
    resurrected: float = Field(
        default=0.0, description="Revenue from customers returning after dormancy."
    )
    retained: float = Field(
        default=0.0, description="Revenue that repeated from the previous period."
    )
    expansion: float = Field(
        default=0.0, description="Increase from customers who spent more."
    )
    contraction: float = Field(
        default=0.0, description="Decrease from customers who spent less."
    )
    churned: float = Field(
        default=0.0, description="Previous revenue from customers now dormant."
    )
    gross_retention_rate: float | None = None
    quick_ratio: float | None = Field(
        default=None,
        description=(
            "Revenue gained divided by revenue lost. Below 1.0 total revenue "
            "is shrinking. Null when nothing was lost, where it is unbounded."
        ),
    )
    net_churn_rate: float | None = Field(
        default=None,
        description=(
            "Net loss as a fraction of previous revenue. Negative means "
            "expansion and resurrection outpaced churn and contraction."
        ),
    )


class ConcentrationResponse(BaseSchema):
    """How concentrated revenue is across customers."""

    customers: int = 0
    revenue: float = 0.0
    top_decile_share: float | None = None
    top_quintile_share: float | None = None
    top_half_share: float | None = None
    largest_customer_share: float | None = None
    gini: float | None = Field(
        default=None,
        description="0 is perfectly even, 1 is maximally concentrated.",
    )


class GrowthAccountingResponse(BaseSchema):
    """A full growth accounting pass."""

    granularity: str
    periods: list[PeriodFlowsRow] = Field(default_factory=list)
    concentration: ConcentrationResponse
