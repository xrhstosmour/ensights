"""Profitability scenarios over the recorded history and its forecast.

Bridges the observed data and the scenario arithmetic. What is observed, the
revenue and the customer counts, comes from the database. What is assumed, the
margin and the acquisition cost, comes from the caller and is echoed back with
every result so the two can never be confused.
"""

from __future__ import annotations

from typing import TYPE_CHECKING
from typing import Any

from app.analysis.profitability import SCENARIO_DISCLAIMER
from app.analysis.profitability import Assumptions
from app.analysis.profitability import InvalidAssumptionsError
from app.analysis.profitability import ProfitabilityError
from app.analysis.profitability import project
from app.analysis.profitability import sweep
from app.analysis.profitability import unit_economics
from app.core.logging import get_logger
from app.repositories.business_metrics_repository import BusinessMetricsRepository
from app.services.forecasting_service import ForecastingService

if TYPE_CHECKING:
    from collections.abc import Sequence
    from datetime import datetime

    from sqlalchemy.ext.asyncio import AsyncSession

logger = get_logger("service.profitability")

__all__ = [
    "InvalidAssumptionsError",
    "ProfitabilityError",
    "ProfitabilityService",
]


class ProfitabilityService:
    """Projects profitability under explicit, caller-supplied assumptions."""

    def __init__(self, session: AsyncSession) -> None:
        """Initialise the service.

        Args:
            session: Async database session.
        """
        self.metrics = BusinessMetricsRepository(session)
        self.forecasting = ForecastingService(session)

    async def project_forward(
        self,
        gross_margin: float,
        customer_acquisition_cost: float,
        operating_cost_per_period: float = 0.0,
        granularity: str = "month",
        horizon: int = 6,
        start: datetime | None = None,
        end: datetime | None = None,
    ) -> dict[str, Any]:
        """Project profitability across observed and forecast periods.

        The observed history and the forecast are projected as one series, and
        the boundary between them is reported, because a projection resting on
        forecast revenue is weaker than one resting on recorded revenue and the
        reader is entitled to know where that line falls.

        Args:
            gross_margin: Assumed fraction of revenue left after cost of goods.
            customer_acquisition_cost: Assumed spend per new customer.
            operating_cost_per_period: Assumed fixed cost per period.
            granularity: Bucket size for the series.
            horizon: Number of forecast periods to append.
            start: Inclusive lower bound on order time.
            end: Exclusive upper bound on order time.

        Returns:
            The projection, its assumptions and the observed/forecast split.

        Raises:
            InvalidAssumptionsError: If the assumptions are out of range.
            ForecastError: If there is too little history to forecast.
        """
        assumptions = Assumptions(
            gross_margin=gross_margin,
            customer_acquisition_cost=customer_acquisition_cost,
            operating_cost_per_period=operating_cost_per_period,
        )
        assumptions.validate()

        periods, forecast_result = await self.forecasting.forecast_revenue(
            granularity=granularity, horizon=horizon, start=start, end=end
        )
        _, observed = await self.forecasting.revenue_series(granularity, start, end)

        revenues = [*observed, *forecast_result.forecast]
        result = project(revenues, assumptions)

        return {
            "granularity": granularity,
            "observed_periods": len(observed),
            "forecast_periods": len(forecast_result.forecast),
            "history_periods": periods,
            "projections": [
                {
                    "index": row.index,
                    "is_forecast": row.index >= len(observed),
                    "revenue": row.revenue,
                    "gross_profit": row.gross_profit,
                    "acquisition_spend": row.acquisition_spend,
                    "operating_cost": row.operating_cost,
                    "net_profit": row.net_profit,
                    "cumulative_net_profit": row.cumulative_net_profit,
                }
                for row in result.projections
            ],
            "break_even_index": result.break_even_index,
            "assumptions": {
                "gross_margin": gross_margin,
                "customer_acquisition_cost": customer_acquisition_cost,
                "operating_cost_per_period": operating_cost_per_period,
            },
            "forecast_skill_score": forecast_result.skill_score,
            "disclaimer": SCENARIO_DISCLAIMER,
        }

    async def _average_customer_revenue(
        self,
        start: datetime | None,
        end: datetime | None,
    ) -> tuple[float, float]:
        """Measure average revenue and lifespan per customer.

        Args:
            start: Inclusive lower bound on order time.
            end: Exclusive upper bound on order time.

        Returns:
            Average observed revenue per customer and the average number of
            orders they placed.
        """
        rows = await self.metrics.rfm(start=start, end=end)
        if not rows:
            return 0.0, 0.0

        revenue = sum(float(row["monetary"] or 0) for row in rows) / len(rows)
        frequency = sum(float(row["frequency"] or 0) for row in rows) / len(rows)
        return revenue, frequency

    async def unit_economics(
        self,
        gross_margin: float,
        customer_acquisition_cost: float,
        start: datetime | None = None,
        end: datetime | None = None,
    ) -> dict[str, Any]:
        """Derive per-customer economics from observed revenue.

        Args:
            gross_margin: Assumed fraction of revenue left after cost of goods.
            customer_acquisition_cost: Assumed spend per new customer.
            start: Inclusive lower bound on order time.
            end: Exclusive upper bound on order time.

        Returns:
            Lifetime value, the LTV:CAC ratio and the payback period, with the
            observed inputs and the assumptions that shaped them.

        Raises:
            InvalidAssumptionsError: If the assumptions are out of range.
        """
        revenue, frequency = await self._average_customer_revenue(start, end)

        economics = unit_economics(
            revenue,
            Assumptions(
                gross_margin=gross_margin,
                customer_acquisition_cost=customer_acquisition_cost,
            ),
            average_periods_per_customer=frequency or None,
        )
        economics["average_customer_revenue"] = revenue
        economics["average_orders_per_customer"] = frequency
        return economics

    async def sensitivity(
        self,
        gross_margins: Sequence[float],
        acquisition_costs: Sequence[float],
        start: datetime | None = None,
        end: datetime | None = None,
    ) -> list[dict[str, Any]]:
        """Evaluate unit economics across a grid of assumptions.

        Args:
            gross_margins: Margin values to evaluate.
            acquisition_costs: Acquisition cost values to evaluate.
            start: Inclusive lower bound on order time.
            end: Exclusive upper bound on order time.

        Returns:
            One row per combination of assumptions.

        Raises:
            InvalidAssumptionsError: If a combination is unusable.
        """
        revenue, frequency = await self._average_customer_revenue(start, end)
        return sweep(
            revenue,
            gross_margins,
            acquisition_costs,
            average_periods_per_customer=frequency or None,
        )
