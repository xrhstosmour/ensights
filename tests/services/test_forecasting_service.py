"""Unit tests for the revenue forecasting service."""

from __future__ import annotations

from collections.abc import Generator
from pathlib import Path

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import SYSTEM_TENANT_ID
from app.core.tenant import tenant_context
from app.ingestion.online_retail import OnlineRetailCSVAdapter
from app.services.forecasting_service import ForecastingService
from app.services.forecasting_service import InvalidForecastParametersError
from app.services.ingestion_service import IngestionService

FIXTURES = Path(__file__).resolve().parent.parent / "fixtures"
COHORTS = FIXTURES / "online_retail_cohorts.csv"


@pytest.fixture(autouse=True)
def _tenant_context() -> Generator[None]:
    """Scope every test to the system tenant.

    Mirrors the fallback tenant production code uses when no explicit
    tenant is supplied, so these tenant-scoped repositories can be
    exercised without a dedicated `Tenant` fixture per test.
    """
    with tenant_context(SYSTEM_TENANT_ID):
        yield


async def _seed(session: AsyncSession) -> ForecastingService:
    """Import the multi-month fixture and return a service over it.

    Args:
        session: Async database session.

    Returns:
        A service bound to the seeded session.
    """
    await IngestionService(session).import_from(OnlineRetailCSVAdapter(COHORTS))
    return ForecastingService(session)


class TestForecastingService:
    """Tests for series construction and forecasting."""

    @pytest.fixture
    def anyio_backend(self) -> str:
        """Provide asyncio backend for anyio-marked tests.

        Returns:
            The backend name.
        """
        return "asyncio"

    @pytest.mark.anyio
    async def test_series_is_built_per_period(self, session: AsyncSession) -> None:
        """The fixture's three months should give three observations.

        Args:
            session: Async database session fixture.

        Returns:
            None.
        """
        service = await _seed(session)

        periods, values = await service.revenue_series(granularity="month")

        assert len(periods) == 3
        assert len(values) == 3
        assert [period.month for period in periods] == [12, 1, 2]

    @pytest.mark.anyio
    async def test_series_forecasts_net_not_gross_value(
        self, session: AsyncSession
    ) -> None:
        """Refunds are money that left, so the series is net of them.

        Args:
            session: Async database session fixture.

        Returns:
            None.
        """
        service = await _seed(session)

        _, values = await service.revenue_series(granularity="month")

        # February grosses 28.50 with 2.00 refunded, so the series holds 26.50.
        assert values[2] == pytest.approx(26.5)

    @pytest.mark.anyio
    async def test_too_little_history_is_rejected(self, session: AsyncSession) -> None:
        """Three months cannot support a forecast worth reporting.

        Args:
            session: Async database session fixture.

        Returns:
            None.
        """
        service = await _seed(session)

        with pytest.raises(InvalidForecastParametersError, match="At least"):
            await service.forecast_revenue(granularity="month", horizon=2)

    @pytest.mark.anyio
    async def test_unsupported_granularity_is_rejected(
        self, session: AsyncSession
    ) -> None:
        """An unknown bucket size should raise rather than guess.

        Args:
            session: Async database session fixture.

        Returns:
            None.
        """
        service = await _seed(session)

        with pytest.raises(InvalidForecastParametersError):
            await service.revenue_series(granularity="fortnight")

    @pytest.mark.anyio
    async def test_daily_series_supports_a_forecast(
        self, session: AsyncSession
    ) -> None:
        """At daily granularity the fixture has enough points to fit.

        Args:
            session: Async database session fixture.

        Returns:
            None.
        """
        service = await _seed(session)

        periods, result = await service.forecast_revenue(
            granularity="day", horizon=2, method="naive"
        )

        assert len(result.forecast) == 2
        assert result.history_length == len(periods)
        # The naive baseline is always measured alongside, even when the
        # method under test is itself the baseline.
        assert result.baseline_metrics is not None
