"""Unit tests for the growth accounting service."""

from __future__ import annotations

from pathlib import Path

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.ingestion.online_retail import OnlineRetailCSVAdapter
from app.services.growth_accounting_service import GrowthAccountingService
from app.services.growth_accounting_service import InvalidActivityError
from app.services.ingestion_service import IngestionService

FIXTURES = Path(__file__).resolve().parent.parent / "fixtures"
COHORTS = FIXTURES / "online_retail_cohorts.csv"


async def _seed(session: AsyncSession) -> GrowthAccountingService:
    """Import the multi-month fixture and return a service over it.

    Args:
        session: Async database session.

    Returns:
        A service bound to the seeded session.
    """
    await IngestionService(session).import_from(OnlineRetailCSVAdapter(COHORTS))
    return GrowthAccountingService(session)


class TestGrowthAccountingService:
    """Tests for the activity log and the decomposition over real data."""

    @pytest.fixture
    def anyio_backend(self) -> str:
        """Provide asyncio backend for anyio-marked tests.

        Returns:
            The backend name.
        """
        return "asyncio"

    @pytest.mark.anyio
    async def test_activity_is_one_row_per_customer_and_period(
        self, session: AsyncSession
    ) -> None:
        """The log should carry a customer, a period and a revenue.

        Args:
            session: Async database session fixture.

        Returns:
            None.
        """
        service = await _seed(session)

        rows = await service.activity(granularity="month")

        assert rows
        for row in rows:
            assert set(row) == {"customer", "period", "revenue"}
        # No customer appears twice in the same period.
        keys = [(row["customer"], row["period"]) for row in rows]
        assert len(keys) == len(set(keys))

    @pytest.mark.anyio
    async def test_decomposition_covers_every_month(
        self, session: AsyncSession
    ) -> None:
        """The fixture's three months should each be decomposed.

        Args:
            session: Async database session fixture.

        Returns:
            None.
        """
        service = await _seed(session)

        result = await service.run(granularity="month")

        assert [flows.period.month for flows in result.periods] == [12, 1, 2]

    @pytest.mark.anyio
    async def test_first_month_is_entirely_new_revenue(
        self, session: AsyncSession
    ) -> None:
        """Both December buyers are new, so nothing is retained.

        Args:
            session: Async database session fixture.

        Returns:
            None.
        """
        service = await _seed(session)

        result = await service.run(granularity="month")

        december = result.periods[0]
        assert december.new == pytest.approx(december.revenue)
        assert december.retained == 0.0

    @pytest.mark.anyio
    async def test_accounting_identity_holds_on_real_data(
        self, session: AsyncSession
    ) -> None:
        """The decomposition must balance against actual imported sales.

        Args:
            session: Async database session fixture.

        Returns:
            None.
        """
        service = await _seed(session)

        result = await service.run(granularity="month")

        for flows in result.periods:
            assert flows.revenue == pytest.approx(
                flows.retained + flows.expansion + flows.new + flows.resurrected
            )
            assert flows.previous_revenue == pytest.approx(
                flows.retained + flows.contraction + flows.churned
            )

    @pytest.mark.anyio
    async def test_resurrection_is_detected(self, session: AsyncSession) -> None:
        """Customer 11111 buys every month, 22222 lapses after December.

        Args:
            session: Async database session fixture.

        Returns:
            None.
        """
        service = await _seed(session)

        result = await service.run(granularity="month")

        # 22222 goes dormant in January, so January records churn.
        assert result.periods[1].churned > 0

    @pytest.mark.anyio
    async def test_concentration_is_measured(self, session: AsyncSession) -> None:
        """The fixture's four buyers should be summarised.

        Args:
            session: Async database session fixture.

        Returns:
            None.
        """
        service = await _seed(session)

        result = await service.run(granularity="month")

        assert result.concentration.customers == 4
        assert result.concentration.gini is not None
        assert result.concentration.largest_customer_share is not None

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

        with pytest.raises(InvalidActivityError):
            await service.activity(granularity="fortnight")

    @pytest.mark.anyio
    async def test_empty_database_returns_nothing(self, session: AsyncSession) -> None:
        """No sales should give no periods rather than an error.

        Args:
            session: Async database session fixture.

        Returns:
            None.
        """
        result = await GrowthAccountingService(session).run()

        assert result.periods == []
        assert result.concentration.customers == 0
