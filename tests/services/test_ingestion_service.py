"""Unit tests for the ingestion service."""

from __future__ import annotations

from pathlib import Path

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.ingestion.online_retail import OnlineRetailCSVAdapter
from app.repositories.commerce_repository import CustomerRepository
from app.repositories.commerce_repository import OrderItemRepository
from app.repositories.commerce_repository import OrderRepository
from app.repositories.commerce_repository import ProductRepository
from app.repositories.commerce_repository import ProductReturnRepository
from app.repositories.commerce_repository import RegionRepository
from app.services.ingestion_service import IngestionService

FIXTURE = (
    Path(__file__).resolve().parent.parent / "fixtures" / "online_retail_sample.csv"
)


class TestIngestionService:
    """Tests for IngestionService.import_from()."""

    @pytest.fixture
    def anyio_backend(self) -> str:
        """Provide asyncio backend for anyio-marked tests.

        Returns:
            The backend name.
        """
        return "asyncio"

    @pytest.mark.anyio
    async def test_import_creates_the_expected_entities(
        self, session: AsyncSession
    ) -> None:
        """A first import should create orders, lines, returns and lookups.

        Args:
            session: Async database session fixture.

        Returns:
            None.
        """
        service = IngestionService(session)

        summary = await service.import_from(OnlineRetailCSVAdapter(FIXTURE))

        # Nine sale transactions in the fixture, two cancellation invoices.
        assert summary.orders_created == 9
        assert summary.returns_created == 3
        assert summary.regions_created == 3
        assert summary.customers_created == 5
        assert summary.transactions_skipped == 0

    @pytest.mark.anyio
    async def test_import_is_idempotent(self, session: AsyncSession) -> None:
        """Re-importing the same file should add nothing and skip everything.

        Args:
            session: Async database session fixture.

        Returns:
            None.
        """
        service = IngestionService(session)
        await service.import_from(OnlineRetailCSVAdapter(FIXTURE))

        second = await service.import_from(OnlineRetailCSVAdapter(FIXTURE))

        assert second.orders_created == 0
        assert second.order_items_created == 0
        assert second.returns_created == 0
        assert second.transactions_skipped == 11

    @pytest.mark.anyio
    async def test_cancellation_invoice_becomes_returns(
        self, session: AsyncSession
    ) -> None:
        """A C-prefixed invoice should produce returns, not an order.

        Args:
            session: Async database session fixture.

        Returns:
            None.
        """
        await IngestionService(session).import_from(OnlineRetailCSVAdapter(FIXTURE))

        assert await OrderRepository(session).get_by_order_number("C536379") is None

        returned = await ProductReturnRepository(session).get_by_return_order_number(
            "C536379"
        )
        assert returned is not None
        # Stored as magnitude even though the source reports -1.
        assert returned.quantity == 1

    @pytest.mark.anyio
    async def test_negative_line_inside_a_sale_becomes_a_linked_return(
        self, session: AsyncSession
    ) -> None:
        """A correction line should be a return pointing at its own order.

        Args:
            session: Async database session fixture.

        Returns:
            None.
        """
        await IngestionService(session).import_from(OnlineRetailCSVAdapter(FIXTURE))

        order = await OrderRepository(session).get_by_order_number("536546")
        assert order is not None

        returned = await ProductReturnRepository(session).get_by_return_order_number(
            "536546"
        )
        assert returned is not None
        assert returned.original_order_id == order.id
        assert returned.quantity == 1

        # The positive line on the same invoice stays a sale.
        lines = await OrderItemRepository(session).list_by_order(order.id)
        assert len(lines) == 1
        assert lines[0].quantity == 4

    @pytest.mark.anyio
    async def test_anonymous_sales_are_imported_without_a_customer(
        self, session: AsyncSession
    ) -> None:
        """Sales with no buyer identifier should still be recorded.

        Args:
            session: Async database session fixture.

        Returns:
            None.
        """
        await IngestionService(session).import_from(OnlineRetailCSVAdapter(FIXTURE))

        order = await OrderRepository(session).get_by_order_number("536544")

        assert order is not None
        assert order.customer_id is None
        assert order.region_id is not None

    @pytest.mark.anyio
    async def test_lookups_are_reused_across_transactions(
        self, session: AsyncSession
    ) -> None:
        """A repeated product or region should be created exactly once.

        Args:
            session: Async database session fixture.

        Returns:
            None.
        """
        await IngestionService(session).import_from(OnlineRetailCSVAdapter(FIXTURE))

        region_repository = RegionRepository(session)
        product_repository = ProductRepository(session)

        united_kingdom = await region_repository.get_by_name("United Kingdom")
        assert united_kingdom is not None

        # 84879 is sold on two different invoices in the fixture.
        product = await product_repository.get_by_stock_code("84879")
        assert product is not None
        assert product.description == "ASSORTED COLOUR BIRD ORNAMENT"

    @pytest.mark.anyio
    async def test_order_totals_are_stored_per_line(
        self, session: AsyncSession
    ) -> None:
        """Each sale line should carry its own price and computed total.

        Args:
            session: Async database session fixture.

        Returns:
            None.
        """
        await IngestionService(session).import_from(OnlineRetailCSVAdapter(FIXTURE))

        order = await OrderRepository(session).get_by_order_number("536365")
        assert order is not None

        lines = await OrderItemRepository(session).list_by_order(order.id)

        assert len(lines) == 3
        assert sum(line.line_total for line in lines) == sum(
            line.quantity * line.unit_price for line in lines
        )

    @pytest.mark.anyio
    async def test_customer_is_linked_to_their_region(
        self, session: AsyncSession
    ) -> None:
        """A newly created buyer should be attached to the sale's region.

        Args:
            session: Async database session fixture.

        Returns:
            None.
        """
        await IngestionService(session).import_from(OnlineRetailCSVAdapter(FIXTURE))

        customer = await CustomerRepository(session).get_by_external_identifier("12583")
        france = await RegionRepository(session).get_by_name("France")

        assert customer is not None
        assert france is not None
        assert customer.region_id == france.id
