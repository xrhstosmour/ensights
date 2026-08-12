"""Unit tests for the business metrics service.

The cohort fixture spans three months and is small enough to reason about by
hand, so every retention and RFM figure asserted here is independently
checkable:

    11111  Dec 2010, Jan 2011, Feb 2011, plus a Feb return
    22222  Dec 2010 only
    33333  Jan 2011, Feb 2011
    44444  Feb 2011 only
"""

from __future__ import annotations

from datetime import UTC
from datetime import datetime
from decimal import Decimal
from pathlib import Path

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.ingestion.online_retail import OnlineRetailCSVAdapter
from app.services.business_metrics_service import BusinessMetricsService
from app.services.business_metrics_service import InvalidGranularityError
from app.services.business_metrics_service import InvalidReportingWindowError
from app.services.ingestion_service import IngestionService

FIXTURES = Path(__file__).resolve().parent.parent / "fixtures"
COHORTS = FIXTURES / "online_retail_cohorts.csv"


async def _seed(session: AsyncSession, source: Path) -> BusinessMetricsService:
    """Import a fixture and return a service over it.

    Args:
        session: Async database session.
        source: Fixture to import.

    Returns:
        A service bound to the seeded session.
    """
    await IngestionService(session).import_from(OnlineRetailCSVAdapter(source))
    return BusinessMetricsService(session)


class TestGrossMerchandiseValue:
    """Tests for the GMV report."""

    @pytest.fixture
    def anyio_backend(self) -> str:
        """Provide asyncio backend for anyio-marked tests.

        Returns:
            The backend name.
        """
        return "asyncio"

    @pytest.mark.anyio
    async def test_gmv_is_reported_per_month(self, session: AsyncSession) -> None:
        """Each month with sales should appear once, oldest first.

        Args:
            session: Async database session fixture.

        Returns:
            None.
        """
        service = await _seed(session, COHORTS)

        rows = await service.gross_merchandise_value(granularity="month")

        assert [row["period"].month for row in rows] == [12, 1, 2]
        # December: 10 x 2.00 plus 5 x 4.00.
        assert rows[0]["gross_merchandise_value"] == Decimal("40.0000")

    @pytest.mark.anyio
    async def test_refunds_are_reported_beside_gross_not_inside_it(
        self, session: AsyncSession
    ) -> None:
        """GMV stays gross; the refund is subtracted only in the net column.

        Args:
            session: Async database session fixture.

        Returns:
            None.
        """
        service = await _seed(session, COHORTS)

        rows = await service.gross_merchandise_value(granularity="month")
        february = next(row for row in rows if row["period"].month == 2)

        # February sales: 2 x 2.00 plus 3 x 1.50 plus 8 x 2.50 equals 28.50.
        assert february["gross_merchandise_value"] == Decimal("28.5000")
        assert february["refunds"] == Decimal("2.0000")
        assert february["net_merchandise_value"] == Decimal("26.5000")

    @pytest.mark.anyio
    async def test_unknown_granularity_is_rejected(self, session: AsyncSession) -> None:
        """An unsupported bucket size should raise rather than guess.

        Args:
            session: Async database session fixture.

        Returns:
            None.
        """
        service = await _seed(session, COHORTS)

        with pytest.raises(InvalidGranularityError):
            await service.gross_merchandise_value(granularity="fortnight")

    @pytest.mark.anyio
    async def test_inverted_window_is_rejected(self, session: AsyncSession) -> None:
        """A window ending before it starts should raise.

        Args:
            session: Async database session fixture.

        Returns:
            None.
        """
        service = await _seed(session, COHORTS)

        with pytest.raises(InvalidReportingWindowError):
            await service.gross_merchandise_value(
                start=datetime(2011, 6, 1, tzinfo=UTC),
                end=datetime(2011, 1, 1, tzinfo=UTC),
            )


class TestCustomerSummary:
    """Tests for the repeat purchase rate."""

    @pytest.fixture
    def anyio_backend(self) -> str:
        """Provide asyncio backend for anyio-marked tests.

        Returns:
            The backend name.
        """
        return "asyncio"

    @pytest.mark.anyio
    async def test_repeat_purchase_rate(self, session: AsyncSession) -> None:
        """Two of the four buyers order more than once.

        Args:
            session: Async database session fixture.

        Returns:
            None.
        """
        service = await _seed(session, COHORTS)

        summary = await service.customer_summary()

        assert summary["customers"] == 4
        assert summary["repeat_customers"] == 2
        assert summary["one_time_customers"] == 2
        assert summary["repeat_purchase_rate"] == pytest.approx(0.5)

    @pytest.mark.anyio
    async def test_average_orders_per_customer(self, session: AsyncSession) -> None:
        """Seven sale invoices spread across four buyers.

        Args:
            session: Async database session fixture.

        Returns:
            None.
        """
        service = await _seed(session, COHORTS)

        summary = await service.customer_summary()

        assert summary["average_orders_per_customer"] == pytest.approx(7 / 4)

    @pytest.mark.anyio
    async def test_summary_is_empty_without_sales(self, session: AsyncSession) -> None:
        """With no data the rates should be zero rather than divide by zero.

        Args:
            session: Async database session fixture.

        Returns:
            None.
        """
        summary = await BusinessMetricsService(session).customer_summary()

        assert summary["customers"] == 0
        assert summary["repeat_purchase_rate"] == 0.0
        assert summary["average_order_value"] == 0.0


class TestCohortRetention:
    """Tests for the acquisition-cohort grid."""

    @pytest.fixture
    def anyio_backend(self) -> str:
        """Provide asyncio backend for anyio-marked tests.

        Returns:
            The backend name.
        """
        return "asyncio"

    @pytest.mark.anyio
    async def test_cohorts_are_keyed_by_first_purchase_month(
        self, session: AsyncSession
    ) -> None:
        """Three acquisition months should appear, sized as expected.

        Args:
            session: Async database session fixture.

        Returns:
            None.
        """
        service = await _seed(session, COHORTS)

        rows = await service.cohort_retention()

        sizes = {
            (row["cohort_month"].year, row["cohort_month"].month): row["cohort_size"]
            for row in rows
        }
        assert sizes[(2010, 12)] == 2
        assert sizes[(2011, 1)] == 1
        assert sizes[(2011, 2)] == 1

    @pytest.mark.anyio
    async def test_december_cohort_retains_one_of_two(
        self, session: AsyncSession
    ) -> None:
        """Only 11111 returns after December, so retention is one half.

        Args:
            session: Async database session fixture.

        Returns:
            None.
        """
        service = await _seed(session, COHORTS)

        rows = await service.cohort_retention()
        december = {
            row["period_index"]: row for row in rows if row["cohort_month"].month == 12
        }

        assert december[0]["active_customers"] == 2
        assert december[0]["retention_rate"] == pytest.approx(1.0)
        assert december[1]["active_customers"] == 1
        assert december[1]["retention_rate"] == pytest.approx(0.5)
        assert december[2]["active_customers"] == 1

    @pytest.mark.anyio
    async def test_period_index_counts_months_after_acquisition(
        self, session: AsyncSession
    ) -> None:
        """A cohort's own month is index zero.

        Args:
            session: Async database session fixture.

        Returns:
            None.
        """
        service = await _seed(session, COHORTS)

        rows = await service.cohort_retention()

        for row in rows:
            assert row["period_index"] >= 0
            if row["period_index"] == 0:
                assert row["active_customers"] == row["cohort_size"]

    @pytest.mark.anyio
    async def test_revenue_retention_rate_uses_the_cohorts_own_first_period(
        self, session: AsyncSession
    ) -> None:
        """December's cohort spends less each month, off its own baseline.

        11111 and 22222 together produce 40.00 in December (period 0). Only
        11111 returns, at 8.00 in January and 4.00 in February.

        Args:
            session: Async database session fixture.

        Returns:
            None.
        """
        service = await _seed(session, COHORTS)

        rows = await service.cohort_retention()
        december = {
            row["period_index"]: row for row in rows if row["cohort_month"].month == 12
        }

        assert december[0]["cohort_revenue"] == Decimal("40.0000")
        assert december[0]["revenue_retention_rate"] == pytest.approx(1.0)
        assert december[1]["period_revenue"] == Decimal("8.0000")
        assert december[1]["revenue_retention_rate"] == pytest.approx(0.2)
        assert december[2]["period_revenue"] == Decimal("4.0000")
        assert december[2]["revenue_retention_rate"] == pytest.approx(0.1)


class TestCohortShape:
    """Tests for the per-cohort revenue trend classification."""

    @pytest.fixture
    def anyio_backend(self) -> str:
        """Provide asyncio backend for anyio-marked tests.

        Returns:
            The backend name.
        """
        return "asyncio"

    @pytest.mark.anyio
    async def test_december_cohort_is_sub_linear(self, session: AsyncSession) -> None:
        """December's revenue retention falls from 0.2 to 0.1, a clear decline.

        Args:
            session: Async database session fixture.

        Returns:
            None.
        """
        service = await _seed(session, COHORTS)

        results = {
            result.cohort_month.month: result for result in await service.cohort_shape()
        }

        assert results[12].shape == "sub-linear"
        assert results[12].periods == 2
        assert results[12].slope < 0

    @pytest.mark.anyio
    async def test_cohorts_too_young_to_trend_are_omitted(
        self, session: AsyncSession
    ) -> None:
        """January and February each have only one period after acquisition.

        Args:
            session: Async database session fixture.

        Returns:
            None.
        """
        service = await _seed(session, COHORTS)

        results = await service.cohort_shape()

        months = {result.cohort_month.month for result in results}
        assert months == {12}


class TestRfm:
    """Tests for the RFM feature table."""

    @pytest.fixture
    def anyio_backend(self) -> str:
        """Provide asyncio backend for anyio-marked tests.

        Returns:
            The backend name.
        """
        return "asyncio"

    @pytest.mark.anyio
    async def test_one_row_per_identified_customer(self, session: AsyncSession) -> None:
        """Each buyer appears exactly once, ranked by value.

        Args:
            session: Async database session fixture.

        Returns:
            None.
        """
        service = await _seed(session, COHORTS)

        rows = await service.rfm()

        identifiers = [row["customer_identifier"] for row in rows]
        assert sorted(identifiers) == ["11111", "22222", "33333", "44444"]
        monetary = [row["monetary"] for row in rows]
        assert monetary == sorted(monetary, reverse=True)

    @pytest.mark.anyio
    async def test_frequency_counts_orders(self, session: AsyncSession) -> None:
        """11111 places three sale invoices; the return is not one.

        Args:
            session: Async database session fixture.

        Returns:
            None.
        """
        service = await _seed(session, COHORTS)

        rows = {row["customer_identifier"]: row for row in await service.rfm()}

        assert rows["11111"]["frequency"] == 3
        assert rows["22222"]["frequency"] == 1

    @pytest.mark.anyio
    async def test_monetary_is_observed_revenue(self, session: AsyncSession) -> None:
        """Monetary value sums the customer's own sale lines.

        Args:
            session: Async database session fixture.

        Returns:
            None.
        """
        service = await _seed(session, COHORTS)

        rows = {row["customer_identifier"]: row for row in await service.rfm()}

        # 11111 buys 10, 4 and 2 units at 2.00 each.
        assert rows["11111"]["monetary"] == Decimal("32.0000")

    @pytest.mark.anyio
    async def test_recency_defaults_to_the_latest_order_in_the_data(
        self, session: AsyncSession
    ) -> None:
        """Without a reference date, the newest order anchors recency.

        Args:
            session: Async database session fixture.

        Returns:
            None.
        """
        service = await _seed(session, COHORTS)

        rows = {row["customer_identifier"]: row for row in await service.rfm()}

        # The latest sale is 44444's on 2011-02-15, so that buyer's recency
        # is zero and the December-only buyer's is much larger.
        assert rows["44444"]["recency_days"] == 0
        assert rows["22222"]["recency_days"] > 60

    @pytest.mark.anyio
    async def test_explicit_reference_date_shifts_recency(
        self, session: AsyncSession
    ) -> None:
        """Passing a reference date measures recency against it.

        Args:
            session: Async database session fixture.

        Returns:
            None.
        """
        service = await _seed(session, COHORTS)

        rows = {
            row["customer_identifier"]: row
            for row in await service.rfm(reference=datetime(2011, 3, 15))
        }

        # 44444 last bought at 2011-02-15 15:00, which is 27 whole days
        # before 2011-03-15 00:00. Partial days floor rather than round.
        assert rows["44444"]["recency_days"] == 27

    @pytest.mark.anyio
    async def test_first_and_last_purchase_are_reported(
        self, session: AsyncSession
    ) -> None:
        """The customer's activity span should be available for cohorting.

        Args:
            session: Async database session fixture.

        Returns:
            None.
        """
        service = await _seed(session, COHORTS)

        rows = {row["customer_identifier"]: row for row in await service.rfm()}

        assert rows["11111"]["first_purchase"].month == 12
        assert rows["11111"]["last_purchase"].month == 2
