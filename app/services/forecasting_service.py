"""Sales forecasting over the recorded transaction history.

Turns the GMV time series into a forecast with measured accuracy. The series
comes from the same aggregation the business metrics use, so a forecast can
never disagree with the history it was fitted on.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from app.analysis.forecasting import EXPONENTIAL_SMOOTHING
from app.analysis.forecasting import ForecastError
from app.analysis.forecasting import ForecastResult
from app.analysis.forecasting import InvalidForecastParametersError
from app.analysis.forecasting import forecast
from app.core.logging import get_logger
from app.repositories.business_metrics_repository import BusinessMetricsRepository

if TYPE_CHECKING:
    from datetime import datetime

    from sqlalchemy.ext.asyncio import AsyncSession

logger = get_logger("service.forecasting")

__all__ = [
    "ForecastError",
    "ForecastingService",
    "InvalidForecastParametersError",
]

# Twelve months of history is what a yearly seasonal cycle needs to be
# estimable at monthly granularity.
SEASONAL_PERIODS_BY_GRANULARITY = {
    "month": 12,
    "quarter": 4,
    "week": 52,
    "day": 7,
}


class ForecastingService:
    """Forecasts sales from the recorded history."""

    def __init__(self, session: AsyncSession) -> None:
        """Initialise the service.

        Args:
            session: Async database session.
        """
        self.metrics = BusinessMetricsRepository(session)

    async def revenue_series(
        self,
        granularity: str = "month",
        start: datetime | None = None,
        end: datetime | None = None,
    ) -> tuple[list[datetime], list[float]]:
        """Build the revenue time series.

        Net rather than gross value is forecast: refunds are money that left
        again, and a forecast of gross value would systematically overstate
        what the business can expect to keep.

        Args:
            granularity: Bucket size for the series.
            start: Inclusive lower bound on order time.
            end: Exclusive upper bound on order time.

        Returns:
            The period labels and their net values, oldest first.

        Raises:
            InvalidForecastParametersError: If the granularity is unsupported.
        """
        try:
            rows = await self.metrics.gross_merchandise_value(granularity, start, end)
        except ValueError as error:
            raise InvalidForecastParametersError(str(error)) from error

        periods = [row["period"] for row in rows]
        values = [float(row["net_merchandise_value"] or 0) for row in rows]
        return periods, values

    async def forecast_revenue(
        self,
        granularity: str = "month",
        horizon: int = 3,
        method: str = EXPONENTIAL_SMOOTHING,
        seasonal: bool = True,
        start: datetime | None = None,
        end: datetime | None = None,
    ) -> tuple[list[datetime], ForecastResult]:
        """Forecast revenue forward and backtest the method.

        Args:
            granularity: Bucket size for the series.
            horizon: Number of future periods to forecast.
            method: Either "naive" or "exponential_smoothing".
            seasonal: Whether to attempt a seasonal fit when history allows.
            start: Inclusive lower bound on order time.
            end: Exclusive upper bound on order time.

        Returns:
            The historical period labels and the forecast result.

        Raises:
            InvalidForecastParametersError: If the series cannot be forecast.
        """
        periods, values = await self.revenue_series(granularity, start, end)

        seasonal_periods = (
            SEASONAL_PERIODS_BY_GRANULARITY.get(granularity) if seasonal else None
        )
        result = forecast(
            values,
            horizon=horizon,
            method=method,
            seasonal_periods=seasonal_periods,
        )

        logger.info(
            "revenue_forecast_complete",
            granularity=granularity,
            history=len(values),
            horizon=horizon,
            skill_score=result.skill_score,
        )
        return periods, result
