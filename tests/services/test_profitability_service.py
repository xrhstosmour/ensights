"""Unit tests for the profitability scenario service."""

from __future__ import annotations

from pathlib import Path

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.analysis.profitability import SCENARIO_DISCLAIMER
from app.ingestion.online_retail import OnlineRetailCSVAdapter
from app.services.ingestion_service import IngestionService
from app.services.profitability_service import InvalidAssumptionsError
from app.services.profitability_service import ProfitabilityService

FIXTURES = Path(__file__).resolve().parent.parent / "fixtures"
COHORTS = FIXTURES / "online_retail_cohorts.csv"


async def _seed(session: AsyncSession) -> ProfitabilityService:
    """Import the multi-month fixture and return a service over it.

    Args:
        session: Async database session.

    Returns:
        A service bound to the seeded session.
    """
    await IngestionService(session).import_from(OnlineRetailCSVAdapter(COHORTS))
    return ProfitabilityService(session)


class TestProfitabilityService:
    """Tests for observed inputs combined with assumed costs."""

    @pytest.fixture
    def anyio_backend(self) -> str:
        """Provide asyncio backend for anyio-marked tests.

        Returns:
            The backend name.
        """
        return "asyncio"

    @pytest.mark.anyio
    async def test_unit_economics_uses_observed_revenue(
        self, session: AsyncSession
    ) -> None:
        """Average revenue comes from the data, the margin from the caller.

        Args:
            session: Async database session fixture.

        Returns:
            None.
        """
        service = await _seed(session)

        economics = await service.unit_economics(
            gross_margin=0.5, customer_acquisition_cost=10.0
        )

        assert economics["average_customer_revenue"] > 0
        assert economics["lifetime_value"] == pytest.approx(
            economics["average_customer_revenue"] * 0.5
        )

    @pytest.mark.anyio
    async def test_every_result_carries_the_disclaimer(
        self, session: AsyncSession
    ) -> None:
        """No scenario output may travel without its warning.

        Args:
            session: Async database session fixture.

        Returns:
            None.
        """
        service = await _seed(session)

        economics = await service.unit_economics(
            gross_margin=0.5, customer_acquisition_cost=10.0
        )
        rows = await service.sensitivity([0.3, 0.6], [10.0])

        assert economics["disclaimer"] == SCENARIO_DISCLAIMER
        assert all(row["disclaimer"] == SCENARIO_DISCLAIMER for row in rows)

    @pytest.mark.anyio
    async def test_sensitivity_grid_covers_every_combination(
        self, session: AsyncSession
    ) -> None:
        """The grid is the cross product of the requested ranges.

        Args:
            session: Async database session fixture.

        Returns:
            None.
        """
        service = await _seed(session)

        rows = await service.sensitivity([0.2, 0.5, 0.8], [10.0, 40.0])

        assert len(rows) == 6

    @pytest.mark.anyio
    async def test_conclusion_flips_with_the_assumed_margin(
        self, session: AsyncSession
    ) -> None:
        """Identical data yields opposite verdicts by assumption alone.

        Args:
            session: Async database session fixture.

        Returns:
            None.
        """
        service = await _seed(session)

        generous = await service.unit_economics(
            gross_margin=0.9, customer_acquisition_cost=5.0
        )
        thin = await service.unit_economics(
            gross_margin=0.05, customer_acquisition_cost=100.0
        )

        assert generous["meets_ratio_benchmark"] is True
        assert thin["meets_ratio_benchmark"] is False

    @pytest.mark.anyio
    async def test_invalid_margin_is_rejected(self, session: AsyncSession) -> None:
        """An out-of-range margin should raise before any work happens.

        Args:
            session: Async database session fixture.

        Returns:
            None.
        """
        service = await _seed(session)

        with pytest.raises(InvalidAssumptionsError):
            await service.unit_economics(
                gross_margin=1.5, customer_acquisition_cost=10.0
            )

    @pytest.mark.anyio
    async def test_economics_on_empty_data_are_zero_not_undefined(
        self, session: AsyncSession
    ) -> None:
        """With no customers the value is zero rather than an error.

        Args:
            session: Async database session fixture.

        Returns:
            None.
        """
        economics = await ProfitabilityService(session).unit_economics(
            gross_margin=0.5, customer_acquisition_cost=10.0
        )

        assert economics["average_customer_revenue"] == 0.0
        assert economics["lifetime_value"] == 0.0
