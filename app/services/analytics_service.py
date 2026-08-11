"""Descriptive analytics over the canonical commerce schema.

Answers the seven questions the business actually asked, listed in
`documents/roadmap.md`. The aggregation itself lives in
`AnalyticsRepository`; this layer exists to validate inputs and to keep the
API free of query concerns.
"""

from __future__ import annotations

from typing import TYPE_CHECKING
from typing import Any

from app.core.logging import get_logger
from app.repositories.analytics_repository import AnalyticsRepository

if TYPE_CHECKING:
    from datetime import datetime

    from sqlalchemy.ext.asyncio import AsyncSession

logger = get_logger("service.analytics")

MAX_LIMIT = 200


class AnalyticsError(Exception):
    """Base class for descriptive analytics failures."""


class InvalidReportingWindowError(AnalyticsError):
    """Raised when the requested window cannot produce a result."""


class InvalidGranularityError(AnalyticsError):
    """Raised when an unsupported time granularity is requested."""


class AnalyticsService:
    """Descriptive analytics for marketing and sales decisions."""

    def __init__(self, session: AsyncSession) -> None:
        """Initialise the service.

        Args:
            session: Async database session.
        """
        self.repository = AnalyticsRepository(session)

    def _validate(
        self,
        limit: int | None,
        start: datetime | None,
        end: datetime | None,
    ) -> int:
        """Validate the common reporting arguments.

        Args:
            limit: Requested maximum rows, when the report is a ranking.
            start: Inclusive lower bound.
            end: Exclusive upper bound.

        Returns:
            The clamped limit.

        Raises:
            InvalidReportingWindowError: If the window is inverted or the
                limit is not positive.
        """
        if start is not None and end is not None and start >= end:
            message = "The reporting window's start must fall before its end"
            raise InvalidReportingWindowError(message)

        if limit is None:
            return MAX_LIMIT
        if limit < 1:
            message = "Limit must be at least 1"
            raise InvalidReportingWindowError(message)
        return min(limit, MAX_LIMIT)

    async def top_products(
        self,
        limit: int = 10,
        start: datetime | None = None,
        end: datetime | None = None,
    ) -> list[dict[str, Any]]:
        """Products with the highest sales.

        Args:
            limit: Maximum rows to return.
            start: Inclusive lower bound on order time.
            end: Exclusive upper bound on order time.

        Returns:
            Ranked product rows.

        Raises:
            InvalidReportingWindowError: If the arguments are inconsistent.
        """
        return await self.repository.top_products(
            self._validate(limit, start, end), start, end
        )

    async def top_customers(
        self,
        limit: int = 10,
        start: datetime | None = None,
        end: datetime | None = None,
    ) -> list[dict[str, Any]]:
        """Customers with the most purchases by value.

        Args:
            limit: Maximum rows to return.
            start: Inclusive lower bound on order time.
            end: Exclusive upper bound on order time.

        Returns:
            Ranked customer rows.

        Raises:
            InvalidReportingWindowError: If the arguments are inconsistent.
        """
        return await self.repository.top_customers(
            self._validate(limit, start, end), start, end
        )

    async def top_regions(
        self,
        limit: int = 10,
        start: datetime | None = None,
        end: datetime | None = None,
    ) -> list[dict[str, Any]]:
        """Regions with the most sales.

        Args:
            limit: Maximum rows to return.
            start: Inclusive lower bound on order time.
            end: Exclusive upper bound on order time.

        Returns:
            Ranked region rows.

        Raises:
            InvalidReportingWindowError: If the arguments are inconsistent.
        """
        return await self.repository.top_regions(
            self._validate(limit, start, end), start, end
        )

    async def sales_over_time(
        self,
        granularity: str = "month",
        start: datetime | None = None,
        end: datetime | None = None,
    ) -> list[dict[str, Any]]:
        """When sales happen, bucketed by calendar period.

        Args:
            granularity: One of "day", "week", "month", "quarter", "year".
            start: Inclusive lower bound on order time.
            end: Exclusive upper bound on order time.

        Returns:
            Period rows, oldest first.

        Raises:
            InvalidReportingWindowError: If the window is inverted.
            InvalidGranularityError: If the granularity is unsupported.
        """
        self._validate(None, start, end)
        try:
            return await self.repository.sales_over_time(granularity, start, end)
        except ValueError as error:
            raise InvalidGranularityError(str(error)) from error

    async def sales_by_weekday(
        self,
        start: datetime | None = None,
        end: datetime | None = None,
    ) -> list[dict[str, Any]]:
        """Which days of the week sell most.

        Args:
            start: Inclusive lower bound on order time.
            end: Exclusive upper bound on order time.

        Returns:
            Weekday rows, Sunday first.

        Raises:
            InvalidReportingWindowError: If the window is inverted.
        """
        self._validate(None, start, end)
        return await self.repository.sales_by_weekday(start, end)

    async def top_returned_products(
        self,
        limit: int = 10,
        start: datetime | None = None,
        end: datetime | None = None,
    ) -> list[dict[str, Any]]:
        """Products generating the most refunds by value.

        Args:
            limit: Maximum rows to return.
            start: Inclusive lower bound on return time.
            end: Exclusive upper bound on return time.

        Returns:
            Ranked refund rows.

        Raises:
            InvalidReportingWindowError: If the arguments are inconsistent.
        """
        return await self.repository.top_returned_products(
            self._validate(limit, start, end), start, end
        )

    async def sales_by_price_band(
        self,
        start: datetime | None = None,
        end: datetime | None = None,
    ) -> list[dict[str, Any]]:
        """Revenue split across unit-price bands.

        Args:
            start: Inclusive lower bound on order time.
            end: Exclusive upper bound on order time.

        Returns:
            One row per band, in ascending price order.

        Raises:
            InvalidReportingWindowError: If the window is inverted.
        """
        self._validate(None, start, end)
        return await self.repository.sales_by_price_band(start, end)

    async def sales_by_characteristic(
        self,
        start: datetime | None = None,
        end: datetime | None = None,
    ) -> list[dict[str, Any]]:
        """Revenue split across rule-based product characteristics.

        The characteristics are keyword-derived, because this dataset has no
        structured category. Treat them as indicative rather than
        authoritative.

        Args:
            start: Inclusive lower bound on order time.
            end: Exclusive upper bound on order time.

        Returns:
            One row per characteristic, highest revenue first.

        Raises:
            InvalidReportingWindowError: If the window is inverted.
        """
        self._validate(None, start, end)
        return await self.repository.sales_by_characteristic(start, end)
