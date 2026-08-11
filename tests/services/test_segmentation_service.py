"""Unit tests for the nested segmentation service."""

from __future__ import annotations

from pathlib import Path

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.ingestion.online_retail import OnlineRetailCSVAdapter
from app.services.ingestion_service import IngestionService
from app.services.segmentation_service import SegmentationService

FIXTURES = Path(__file__).resolve().parent.parent / "fixtures"
COHORTS = FIXTURES / "online_retail_cohorts.csv"


async def _seed(session: AsyncSession) -> SegmentationService:
    """Import the multi-month fixture and return a service over it.

    Args:
        session: Async database session.

    Returns:
        A service bound to the seeded session.
    """
    await IngestionService(session).import_from(OnlineRetailCSVAdapter(COHORTS))
    return SegmentationService(session)


class TestSegmentationService:
    """Tests for feature construction and the nested run."""

    @pytest.fixture
    def anyio_backend(self) -> str:
        """Provide asyncio backend for anyio-marked tests.

        Returns:
            The backend name.
        """
        return "asyncio"

    @pytest.mark.anyio
    async def test_region_features_are_built_per_region(
        self, session: AsyncSession
    ) -> None:
        """One row per region, carrying its sales shape.

        Args:
            session: Async database session fixture.

        Returns:
            None.
        """
        service = await _seed(session)

        rows = await service.region_features()

        keys = {row["key"] for row in rows}
        assert keys == {"United Kingdom", "France", "Australia"}
        for row in rows:
            assert set(row) == {
                "key",
                "revenue",
                "orders",
                "customers",
                "active_months",
            }

    @pytest.mark.anyio
    async def test_active_months_distinguishes_steady_from_spiky_regions(
        self, session: AsyncSession
    ) -> None:
        """A region trading across months differs from a one-month one.

        Args:
            session: Async database session fixture.

        Returns:
            None.
        """
        service = await _seed(session)

        rows = {row["key"]: row for row in await service.region_features()}

        # The UK trades in December, January and February; Australia only in
        # February. That is exactly the time dimension the feature captures.
        assert rows["United Kingdom"]["active_months"] == 3
        assert rows["Australia"]["active_months"] == 1

    @pytest.mark.anyio
    async def test_customer_features_are_grouped_by_region(
        self, session: AsyncSession
    ) -> None:
        """RFM rows should be bucketed under the region they belong to.

        Args:
            session: Async database session fixture.

        Returns:
            None.
        """
        service = await _seed(session)

        grouped = await service.customer_features_by_region()

        assert set(grouped) == {"United Kingdom", "France", "Australia"}
        assert {row["key"] for row in grouped["France"]} == {"33333"}
        for rows in grouped.values():
            for row in rows:
                assert set(row) == {"key", "recency_days", "frequency", "monetary"}

    @pytest.mark.anyio
    async def test_run_produces_a_tree(self, session: AsyncSession) -> None:
        """The run should return region clusters with customer sub-clusters.

        Args:
            session: Async database session fixture.

        Returns:
            None.
        """
        service = await _seed(session)

        result = await service.run(k_range=(2,))

        assert result.clusters
        for cluster in result.clusters:
            assert cluster.level == 1
            assert cluster.members
            for child in cluster.children:
                assert child.level == 2
                assert child.label.startswith(f"{cluster.label}.")

    @pytest.mark.anyio
    async def test_every_region_appears_exactly_once_in_the_tree(
        self, session: AsyncSession
    ) -> None:
        """A partition must cover every region without duplicating any.

        Args:
            session: Async database session fixture.

        Returns:
            None.
        """
        service = await _seed(session)

        result = await service.run(k_range=(2,))

        assigned = [member for cluster in result.clusters for member in cluster.members]
        assert sorted(assigned) == ["Australia", "France", "United Kingdom"]

    @pytest.mark.anyio
    async def test_run_on_empty_database_returns_nothing(
        self, session: AsyncSession
    ) -> None:
        """No sales should give no clusters rather than an error.

        Args:
            session: Async database session fixture.

        Returns:
            None.
        """
        result = await SegmentationService(session).run()

        assert result.clusters == []
