"""Unit tests for the market basket service."""

from __future__ import annotations

from pathlib import Path

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.analysis.frequent_itemsets import APRIORI
from app.ingestion.online_retail import OnlineRetailCSVAdapter
from app.services.ingestion_service import IngestionService
from app.services.market_basket_service import InvalidMiningParametersError
from app.services.market_basket_service import MarketBasketService

# Five baskets with deliberate overlap, so co-occurrence exists to mine:
#   85123A appears in all five, 71053 in four, 22633 in three.
FIXTURE = (
    Path(__file__).resolve().parent.parent / "fixtures" / "online_retail_baskets.csv"
)


async def _seed(session: AsyncSession) -> MarketBasketService:
    """Import the fixture and return a service over it.

    Args:
        session: Async database session.

    Returns:
        A service bound to the seeded session.
    """
    await IngestionService(session).import_from(OnlineRetailCSVAdapter(FIXTURE))
    return MarketBasketService(session)


class TestMarketBasketService:
    """Tests for basket construction, mining and persistence."""

    @pytest.fixture
    def anyio_backend(self) -> str:
        """Provide asyncio backend for anyio-marked tests.

        Returns:
            The backend name.
        """
        return "asyncio"

    @pytest.mark.anyio
    async def test_baskets_group_lines_by_order(self, session: AsyncSession) -> None:
        """Each basket should carry one order's distinct products.

        Args:
            session: Async database session fixture.

        Returns:
            None.
        """
        service = await _seed(session)

        baskets = await service.build_baskets()

        assert len(baskets) == 5
        assert sorted(len(basket) for basket in baskets) == [2, 2, 3, 3, 4]

    @pytest.mark.anyio
    async def test_single_line_orders_are_excluded(self, session: AsyncSession) -> None:
        """A one-item basket cannot show co-occurrence, so it is dropped.

        Args:
            session: Async database session fixture.

        Returns:
            None.
        """
        service = await _seed(session)

        baskets = await service.build_baskets()

        assert all(len(basket) >= 2 for basket in baskets)

    @pytest.mark.anyio
    async def test_minimum_basket_size_is_configurable(
        self, session: AsyncSession
    ) -> None:
        """Lowering the floor should admit the single-line orders.

        Args:
            session: Async database session fixture.

        Returns:
            None.
        """
        service = await _seed(session)

        permissive = await service.build_baskets(minimum_basket_size=1)
        strict = await service.build_baskets(minimum_basket_size=4)

        assert len(permissive) > len(strict)

    @pytest.mark.anyio
    async def test_run_persists_itemsets_and_rules(self, session: AsyncSession) -> None:
        """A persisted run should be readable back as rules.

        Args:
            session: Async database session fixture.

        Returns:
            None.
        """
        service = await _seed(session)

        run_identifier, result = await service.run(
            minimum_support=0.3, minimum_confidence=0.5
        )

        assert run_identifier
        assert result.itemsets

        rules = await service.latest_rules(minimum_lift=0.0)
        assert len(rules) == len(result.rules)
        if rules:
            assert rules[0]["run_identifier"] == run_identifier

    @pytest.mark.anyio
    async def test_persisted_rules_carry_readable_descriptions(
        self, session: AsyncSession
    ) -> None:
        """Bare stock codes are unreadable, so descriptions are stored too.

        Args:
            session: Async database session fixture.

        Returns:
            None.
        """
        service = await _seed(session)
        await service.run(minimum_support=0.3, minimum_confidence=0.5)

        rules = await service.latest_rules(minimum_lift=0.0)

        assert rules
        for rule in rules:
            assert len(rule["antecedent_descriptions"]) == len(rule["antecedents"])
            assert all(description for description in rule["antecedent_descriptions"])

    @pytest.mark.anyio
    async def test_rules_are_returned_strongest_first(
        self, session: AsyncSession
    ) -> None:
        """Reads should order by lift so the useful rules come first.

        Args:
            session: Async database session fixture.

        Returns:
            None.
        """
        service = await _seed(session)
        await service.run(minimum_support=0.3, minimum_confidence=0.5)

        rules = await service.latest_rules(minimum_lift=0.0)

        lifts = [rule["lift"] for rule in rules]
        assert lifts == sorted(lifts, reverse=True)

    @pytest.mark.anyio
    async def test_minimum_lift_filters_out_chance_associations(
        self, session: AsyncSession
    ) -> None:
        """A lift floor of one excludes rules no better than chance.

        Args:
            session: Async database session fixture.

        Returns:
            None.
        """
        service = await _seed(session)
        await service.run(minimum_support=0.3, minimum_confidence=0.5)

        everything = await service.latest_rules(minimum_lift=0.0)
        meaningful = await service.latest_rules(minimum_lift=1.0)

        assert len(meaningful) <= len(everything)
        assert all(rule["lift"] >= 1.0 for rule in meaningful)

    @pytest.mark.anyio
    async def test_run_without_persistence_writes_nothing(
        self, session: AsyncSession
    ) -> None:
        """An exploratory run should leave no rows behind.

        Args:
            session: Async database session fixture.

        Returns:
            None.
        """
        service = await _seed(session)

        await service.run(minimum_support=0.3, minimum_confidence=0.5, persist=False)

        assert await service.latest_rules(minimum_lift=0.0) == []

    @pytest.mark.anyio
    async def test_latest_rules_is_empty_before_any_run(
        self, session: AsyncSession
    ) -> None:
        """Reading before mining should return nothing, not raise.

        Args:
            session: Async database session fixture.

        Returns:
            None.
        """
        service = await _seed(session)

        assert await service.latest_rules() == []

    @pytest.mark.anyio
    async def test_both_algorithms_agree_on_the_stored_itemsets(
        self, session: AsyncSession
    ) -> None:
        """Apriori and FP-Growth should mine the same sets from one dataset.

        Args:
            session: Async database session fixture.

        Returns:
            None.
        """
        service = await _seed(session)

        _, apriori = await service.run(
            algorithm=APRIORI, minimum_support=0.3, persist=False
        )
        _, fpgrowth = await service.run(minimum_support=0.3, persist=False)

        assert {itemset.items for itemset in apriori.itemsets} == {
            itemset.items for itemset in fpgrowth.itemsets
        }

    @pytest.mark.anyio
    async def test_invalid_parameters_are_rejected(self, session: AsyncSession) -> None:
        """Bad thresholds should raise before any mining happens.

        Args:
            session: Async database session fixture.

        Returns:
            None.
        """
        service = await _seed(session)

        with pytest.raises(InvalidMiningParametersError):
            await service.run(minimum_support=0.0)
