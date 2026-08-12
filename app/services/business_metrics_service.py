"""Business and unit-economics metrics measured from transaction data.

Everything this service reports is observed, not assumed. GMV, repeat purchase
rate, cohort retention and RFM all come straight from the recorded sales.

The questions that cannot be answered this way, whether the business is
profitable and when it will be, need a cost of goods and an acquisition spend
that this data does not contain. Those live in the profitability scenario
service, which is explicitly a what-if tool rather than a measurement.
"""

from __future__ import annotations

from typing import TYPE_CHECKING
from typing import Any

from app.analysis.cohort_shape import CohortShapeResult
from app.analysis.cohort_shape import classify_all
from app.core.logging import get_logger
from app.repositories.business_metrics_repository import BusinessMetricsRepository
from app.services.analytics_service import AnalyticsError
from app.services.analytics_service import InvalidGranularityError
from app.services.analytics_service import InvalidReportingWindowError

if TYPE_CHECKING:
    from datetime import datetime

    from sqlalchemy.ext.asyncio import AsyncSession

logger = get_logger("service.business_metrics")

__all__ = [
    "AnalyticsError",
    "BusinessMetricsService",
    "InvalidGranularityError",
    "InvalidReportingWindowError",
]


class BusinessMetricsService:
    """Measured business metrics for marketing and sales decisions."""

    def __init__(self, session: AsyncSession) -> None:
        """Initialise the service.

        Args:
            session: Async database session.
        """
        self.repository = BusinessMetricsRepository(session)

    def _validate_window(
        self,
        start: datetime | None,
        end: datetime | None,
    ) -> None:
        """Reject a reporting window that cannot produce a result.

        Args:
            start: Inclusive lower bound.
            end: Exclusive upper bound.

        Raises:
            InvalidReportingWindowError: If the window is inverted.
        """
        if start is not None and end is not None and start >= end:
            message = "The reporting window's start must fall before its end"
            raise InvalidReportingWindowError(message)

    async def gross_merchandise_value(
        self,
        granularity: str = "month",
        start: datetime | None = None,
        end: datetime | None = None,
    ) -> list[dict[str, Any]]:
        """Gross merchandise value over time, with refunds alongside.

        Args:
            granularity: One of "day", "week", "month", "quarter", "year".
            start: Inclusive lower bound on order time.
            end: Exclusive upper bound on order time.

        Returns:
            Period rows carrying gross, refunded and net value.

        Raises:
            InvalidReportingWindowError: If the window is inverted.
            InvalidGranularityError: If the granularity is unsupported.
        """
        self._validate_window(start, end)
        try:
            return await self.repository.gross_merchandise_value(
                granularity, start, end
            )
        except ValueError as error:
            raise InvalidGranularityError(str(error)) from error

    async def customer_summary(
        self,
        start: datetime | None = None,
        end: datetime | None = None,
    ) -> dict[str, Any]:
        """Repeat purchase rate and the counts behind it.

        Args:
            start: Inclusive lower bound on order time.
            end: Exclusive upper bound on order time.

        Returns:
            Customer counts, repeat purchase rate and averages.

        Raises:
            InvalidReportingWindowError: If the window is inverted.
        """
        self._validate_window(start, end)
        return await self.repository.customer_summary(start, end)

    async def cohort_retention(
        self,
        start: datetime | None = None,
        end: datetime | None = None,
    ) -> list[dict[str, Any]]:
        """Monthly acquisition cohorts and their later activity.

        Args:
            start: Inclusive lower bound on order time.
            end: Exclusive upper bound on order time.

        Returns:
            Cohort rows with retention rates.

        Raises:
            InvalidReportingWindowError: If the window is inverted.
        """
        self._validate_window(start, end)
        return await self.repository.cohort_retention(start, end)

    async def cohort_shape(
        self,
        start: datetime | None = None,
        end: datetime | None = None,
    ) -> list[CohortShapeResult]:
        """Classify each acquisition cohort's revenue trend.

        Args:
            start: Inclusive lower bound on order time.
            end: Exclusive upper bound on order time.

        Returns:
            One result per cohort with at least two periods after
            acquisition; cohorts too young to trend are omitted.

        Raises:
            InvalidReportingWindowError: If the window is inverted.
        """
        self._validate_window(start, end)
        rows = await self.repository.cohort_retention(start, end)
        return classify_all(rows)

    async def rfm(
        self,
        reference: datetime | None = None,
        start: datetime | None = None,
        end: datetime | None = None,
    ) -> list[dict[str, Any]]:
        """Recency, frequency and monetary value per customer.

        These are the features the customer-level clustering consumes, and the
        monetary column is observed value to date rather than a prediction.

        Args:
            reference: Date to measure recency against, defaulting to the
                latest order in the data.
            start: Inclusive lower bound on order time.
            end: Exclusive upper bound on order time.

        Returns:
            One row per identified customer.

        Raises:
            InvalidReportingWindowError: If the window is inverted.
        """
        self._validate_window(start, end)
        return await self.repository.rfm(reference, start, end)
