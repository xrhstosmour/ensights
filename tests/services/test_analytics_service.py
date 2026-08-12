"""Unit tests for the descriptive analytics service.

Every case runs against data imported through the real adapter, so the numbers
asserted here are the ones the seven business questions would actually return.
"""

from __future__ import annotations

from collections.abc import Generator
from datetime import UTC
from datetime import datetime
from decimal import Decimal
from pathlib import Path

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import SYSTEM_TENANT_ID
from app.core.tenant import tenant_context
from app.ingestion.online_retail import OnlineRetailCSVAdapter
from app.services.analytics_service import AnalyticsService
from app.services.analytics_service import InvalidGranularityError
from app.services.analytics_service import InvalidReportingWindowError
from app.services.ingestion_service import IngestionService

FIXTURE = (
    Path(__file__).resolve().parent.parent / "fixtures" / "online_retail_sample.csv"
)


@pytest.fixture(autouse=True)
def _tenant_context() -> Generator[None]:
    """Scope every test to the system tenant.

    Mirrors the fallback tenant production code uses when no explicit
    tenant is supplied, so these tenant-scoped repositories can be
    exercised without a dedicated `Tenant` fixture per test.
    """
    with tenant_context(SYSTEM_TENANT_ID):
        yield


async def _seed(session: AsyncSession) -> AnalyticsService:
    """Import the fixture and return a service over it.

    Args:
        session: Async database session.

    Returns:
        A service bound to the seeded session.
    """
    await IngestionService(session).import_from(OnlineRetailCSVAdapter(FIXTURE))
    return AnalyticsService(session)


class TestDescriptiveAnalytics:
    """Tests for the seven descriptive reports."""

    @pytest.fixture
    def anyio_backend(self) -> str:
        """Provide asyncio backend for anyio-marked tests.

        Returns:
            The backend name.
        """
        return "asyncio"

    @pytest.mark.anyio
    async def test_top_products_ranks_by_revenue(self, session: AsyncSession) -> None:
        """Products should come back ordered by revenue, highest first.

        Args:
            session: Async database session fixture.

        Returns:
            None.
        """
        service = await _seed(session)

        rows = await service.top_products(limit=3)

        assert len(rows) == 3
        revenues = [row["revenue"] for row in rows]
        assert revenues == sorted(revenues, reverse=True)
        # 22086 sells 80 units at 2.55 on one invoice plus 1 more later.
        assert rows[0]["stock_code"] == "22086"
        assert rows[0]["units"] == 81

    @pytest.mark.anyio
    async def test_top_customers_excludes_anonymous_sales(
        self, session: AsyncSession
    ) -> None:
        """Only identified buyers should appear in the customer ranking.

        Args:
            session: Async database session fixture.

        Returns:
            None.
        """
        service = await _seed(session)

        rows = await service.top_customers(limit=10)

        identifiers = {row["customer_identifier"] for row in rows}
        assert identifiers == {"17850", "13047", "12583", "13748", "12431"}
        assert all(row["customer_identifier"] is not None for row in rows)

    @pytest.mark.anyio
    async def test_top_regions_aggregates_by_region(
        self, session: AsyncSession
    ) -> None:
        """Regions should aggregate their orders, customers and revenue.

        Args:
            session: Async database session fixture.

        Returns:
            None.
        """
        service = await _seed(session)

        rows = await service.top_regions()

        by_region = {row["region"]: row for row in rows}
        assert set(by_region) == {"United Kingdom", "France", "Australia"}
        assert by_region["France"]["orders"] == 1
        assert by_region["France"]["units"] == 48

    @pytest.mark.anyio
    async def test_sales_over_time_buckets_by_month(
        self, session: AsyncSession
    ) -> None:
        """Monthly buckets should cover the fixture's single month.

        Args:
            session: Async database session fixture.

        Returns:
            None.
        """
        service = await _seed(session)

        rows = await service.sales_over_time(granularity="month")

        assert len(rows) == 1
        assert rows[0]["period"].year == 2010
        assert rows[0]["period"].month == 12
        assert rows[0]["orders"] == 9

    @pytest.mark.anyio
    async def test_sales_over_time_rejects_unknown_granularity(
        self, session: AsyncSession
    ) -> None:
        """An unsupported bucket size should raise rather than guess.

        Args:
            session: Async database session fixture.

        Returns:
            None.
        """
        service = await _seed(session)

        with pytest.raises(InvalidGranularityError):
            await service.sales_over_time(granularity="fortnight")

    @pytest.mark.anyio
    async def test_sales_by_weekday_returns_one_row_per_day_present(
        self, session: AsyncSession
    ) -> None:
        """Weekday aggregation should cover only the days that saw sales.

        Args:
            session: Async database session fixture.

        Returns:
            None.
        """
        service = await _seed(session)

        rows = await service.sales_by_weekday()

        # Every fixture sale falls on 2010-12-01, a Wednesday, which is 3.
        assert len(rows) == 1
        assert int(rows[0]["weekday"]) == 3

    @pytest.mark.anyio
    async def test_top_returned_products_ranks_by_refunded_value(
        self, session: AsyncSession
    ) -> None:
        """Refund ranking should surface the products actually returned.

        Args:
            session: Async database session fixture.

        Returns:
            None.
        """
        service = await _seed(session)

        rows = await service.top_returned_products()

        codes = {row["stock_code"] for row in rows}
        assert codes == {"22745", "22728", "22633"}
        values = [row["returned_value"] for row in rows]
        assert values == sorted(values, reverse=True)
        # 22728 is returned twice at 3.75 on the cancellation invoice.
        by_code = {row["stock_code"]: row for row in rows}
        assert by_code["22728"]["returned_units"] == 2
        assert by_code["22728"]["returned_value"] == Decimal("7.5000")

    @pytest.mark.anyio
    async def test_sales_by_price_band_covers_every_band(
        self, session: AsyncSession
    ) -> None:
        """All bands should be reported, including ones with no sales.

        Args:
            session: Async database session fixture.

        Returns:
            None.
        """
        service = await _seed(session)

        rows = await service.sales_by_price_band()

        labels = [row["band"] for row in rows]
        assert labels[:5] == ["0-1", "1-5", "5-10", "10-50", "50+"]
        # Nothing in the fixture is priced at 10 or more.
        assert rows[3]["revenue"] == Decimal("0")
        assert rows[4]["revenue"] == Decimal("0")
        # The 1-5 band holds most of the fixture's lines.
        assert rows[1]["units"] > 0

    @pytest.mark.anyio
    async def test_price_bands_sum_to_total_revenue(
        self, session: AsyncSession
    ) -> None:
        """Banding must partition revenue, never duplicate or drop it.

        Args:
            session: Async database session fixture.

        Returns:
            None.
        """
        service = await _seed(session)

        bands = await service.sales_by_price_band()
        periods = await service.sales_over_time(granularity="year")

        banded_total = sum(row["revenue"] for row in bands)
        assert banded_total == periods[0]["revenue"]

    @pytest.mark.anyio
    async def test_characteristics_partition_revenue(
        self, session: AsyncSession
    ) -> None:
        """Each product lands in exactly one characteristic bucket.

        Args:
            session: Async database session fixture.

        Returns:
            None.
        """
        service = await _seed(session)

        rows = await service.sales_by_characteristic()
        periods = await service.sales_over_time(granularity="year")

        assert sum(row["revenue"] for row in rows) == periods[0]["revenue"]
        assert len({row["characteristic"] for row in rows}) == len(rows)

    @pytest.mark.anyio
    async def test_characteristics_tag_known_keywords(
        self, session: AsyncSession
    ) -> None:
        """Recognisable descriptions should land in a named bucket.

        Args:
            session: Async database session fixture.

        Returns:
            None.
        """
        service = await _seed(session)

        rows = await service.sales_by_characteristic()

        labels = {row["characteristic"] for row in rows}
        # The fixture contains Christmas lights, a playhouse toy and lanterns.
        assert "christmas" in labels
        assert "toy" in labels

    @pytest.mark.anyio
    async def test_reporting_window_filters_results(
        self, session: AsyncSession
    ) -> None:
        """A window should exclude sales outside it.

        Args:
            session: Async database session fixture.

        Returns:
            None.
        """
        service = await _seed(session)

        morning = await service.top_products(
            limit=50,
            start=datetime(2010, 12, 1, 8, 0, tzinfo=UTC),
            end=datetime(2010, 12, 1, 9, 0, tzinfo=UTC),
        )
        everything = await service.top_products(limit=50)

        assert len(morning) < len(everything)

    @pytest.mark.anyio
    async def test_inverted_window_is_rejected(self, session: AsyncSession) -> None:
        """A window ending before it starts should raise.

        Args:
            session: Async database session fixture.

        Returns:
            None.
        """
        service = await _seed(session)

        with pytest.raises(InvalidReportingWindowError):
            await service.top_products(
                start=datetime(2011, 1, 1, tzinfo=UTC),
                end=datetime(2010, 1, 1, tzinfo=UTC),
            )

    @pytest.mark.anyio
    async def test_non_positive_limit_is_rejected(self, session: AsyncSession) -> None:
        """A limit below one should raise rather than return everything.

        Args:
            session: Async database session fixture.

        Returns:
            None.
        """
        service = await _seed(session)

        with pytest.raises(InvalidReportingWindowError):
            await service.top_products(limit=0)

    @pytest.mark.anyio
    async def test_limit_is_clamped_to_the_maximum(self, session: AsyncSession) -> None:
        """An oversized limit should be clamped, not refused.

        Args:
            session: Async database session fixture.

        Returns:
            None.
        """
        service = await _seed(session)

        rows = await service.top_products(limit=10_000)

        assert len(rows) <= 200

    @pytest.mark.anyio
    async def test_returns_are_not_counted_as_revenue(
        self, session: AsyncSession
    ) -> None:
        """Refunded lines must stay out of the sales aggregates.

        Args:
            session: Async database session fixture.

        Returns:
            None.
        """
        service = await _seed(session)

        products = {row["stock_code"]: row for row in await service.top_products(50)}

        # 22745 sells 6 units and is returned once; the sale total is untouched
        # by the return, which is reported separately.
        assert products["22745"]["units"] == 6
