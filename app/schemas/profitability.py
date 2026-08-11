"""Response schemas for the profitability scenario endpoints.

Every schema here carries a `disclaimer` field. That is deliberate: these
responses describe what would follow *if* the stated assumptions held, and the
warning travels with the data so a consumer cannot strip it by accident.
"""

from __future__ import annotations

from datetime import datetime

from pydantic import Field

from app.schemas.base import BaseSchema


class ScenarioAssumptions(BaseSchema):
    """The caller-supplied inputs a scenario rests on."""

    gross_margin: float
    customer_acquisition_cost: float
    operating_cost_per_period: float = 0.0


class PeriodProjectionRow(BaseSchema):
    """One projected period."""

    index: int
    is_forecast: bool = Field(
        description="True when this period's revenue is forecast, not recorded."
    )
    revenue: float
    gross_profit: float
    acquisition_spend: float
    operating_cost: float
    net_profit: float
    cumulative_net_profit: float


class ProfitabilityProjection(BaseSchema):
    """A projection across observed and forecast periods."""

    granularity: str
    observed_periods: int
    forecast_periods: int
    history_periods: list[datetime] = Field(default_factory=list)
    projections: list[PeriodProjectionRow] = Field(default_factory=list)
    break_even_index: int | None = Field(
        default=None,
        description=(
            "First period where cumulative net profit turns positive under "
            "these assumptions, or null if it does not within the projection."
        ),
    )
    assumptions: ScenarioAssumptions
    forecast_skill_score: float | None = Field(
        default=None,
        description=(
            "Accuracy of the underlying revenue forecast against a naive "
            "baseline. A weak forecast makes the later periods weaker still."
        ),
    )
    disclaimer: str


class UnitEconomicsResponse(BaseSchema):
    """Per-customer economics under the stated assumptions."""

    average_customer_revenue: float = Field(
        description="Observed, not assumed: mean revenue per identified customer."
    )
    average_orders_per_customer: float
    lifetime_value: float = Field(
        description="Gross profit per customer, being revenue times the margin."
    )
    lifetime_value_to_acquisition_cost: float | None = None
    payback_periods: float | None = None
    healthy_lifetime_value_to_acquisition_cost: float
    healthy_payback_periods: float
    meets_ratio_benchmark: bool | None = None
    assumptions: dict[str, float] = Field(default_factory=dict)
    disclaimer: str


class SensitivityRow(BaseSchema):
    """One cell of the assumption grid."""

    lifetime_value: float
    lifetime_value_to_acquisition_cost: float | None = None
    payback_periods: float | None = None
    healthy_lifetime_value_to_acquisition_cost: float
    healthy_payback_periods: float
    meets_ratio_benchmark: bool | None = None
    assumptions: dict[str, float] = Field(default_factory=dict)
    disclaimer: str
