"""Unit tests for the canonical e-commerce repositories."""

from __future__ import annotations

from datetime import UTC
from datetime import datetime
from decimal import Decimal

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.customer import Customer
from app.models.order import Order
from app.models.order_item import OrderItem
from app.models.product import Product
from app.models.product_return import ProductReturn
from app.models.region import Region
from app.repositories.commerce_repository import CustomerRepository
from app.repositories.commerce_repository import OrderItemRepository
from app.repositories.commerce_repository import OrderRepository
from app.repositories.commerce_repository import ProductRepository
from app.repositories.commerce_repository import ProductReturnRepository
from app.repositories.commerce_repository import RegionRepository


class TestRegionRepository:
    """Tests for RegionRepository operations."""

    @pytest.fixture
    def anyio_backend(self) -> str:
        """Provide asyncio backend for anyio-marked tests.

        Returns:
            The backend name.
        """
        return "asyncio"

    @pytest.mark.anyio
    async def test_get_by_name_returns_region(self, session: AsyncSession) -> None:
        """get_by_name() should return the region with the given name.

        Args:
            session: Async database session fixture.

        Returns:
            None.
        """
        repository = RegionRepository(session)
        created = await repository.create({"name": "United Kingdom", "code": "GB"})

        found = await repository.get_by_name("United Kingdom")

        assert isinstance(found, Region)
        assert found.id == created.id
        assert found.code == "GB"

    @pytest.mark.anyio
    async def test_get_by_name_returns_none_for_unknown(
        self, session: AsyncSession
    ) -> None:
        """get_by_name() should return None when no region matches.

        Args:
            session: Async database session fixture.

        Returns:
            None.
        """
        repository = RegionRepository(session)

        assert await repository.get_by_name("Atlantis") is None

    @pytest.mark.anyio
    async def test_get_by_name_excludes_soft_deleted(
        self, session: AsyncSession
    ) -> None:
        """get_by_name() should ignore soft-deleted regions.

        Args:
            session: Async database session fixture.

        Returns:
            None.
        """
        repository = RegionRepository(session)
        created = await repository.create({"name": "Narnia"})
        await repository.delete(created.id)

        assert await repository.get_by_name("Narnia") is None


class TestCustomerRepository:
    """Tests for CustomerRepository operations."""

    @pytest.fixture
    def anyio_backend(self) -> str:
        """Provide asyncio backend for anyio-marked tests.

        Returns:
            The backend name.
        """
        return "asyncio"

    @pytest.mark.anyio
    async def test_get_by_external_identifier_returns_customer(
        self, session: AsyncSession
    ) -> None:
        """get_by_external_identifier() should return the matching customer.

        Args:
            session: Async database session fixture.

        Returns:
            None.
        """
        repository = CustomerRepository(session)
        created = await repository.create({"external_identifier": "17850"})

        found = await repository.get_by_external_identifier("17850")

        assert isinstance(found, Customer)
        assert found.id == created.id

    @pytest.mark.anyio
    async def test_get_by_external_identifier_returns_none_for_unknown(
        self, session: AsyncSession
    ) -> None:
        """get_by_external_identifier() should return None when nothing matches.

        Args:
            session: Async database session fixture.

        Returns:
            None.
        """
        repository = CustomerRepository(session)

        assert await repository.get_by_external_identifier("00000") is None

    @pytest.mark.anyio
    async def test_customer_links_to_region(self, session: AsyncSession) -> None:
        """A customer should persist its region foreign key.

        Args:
            session: Async database session fixture.

        Returns:
            None.
        """
        region = await RegionRepository(session).create({"name": "France"})
        repository = CustomerRepository(session)

        created = await repository.create(
            {"external_identifier": "12680", "region_id": region.id}
        )

        assert created.region_id == region.id


class TestProductRepository:
    """Tests for ProductRepository operations."""

    @pytest.fixture
    def anyio_backend(self) -> str:
        """Provide asyncio backend for anyio-marked tests.

        Returns:
            The backend name.
        """
        return "asyncio"

    @pytest.mark.anyio
    async def test_get_by_stock_code_returns_product(
        self, session: AsyncSession
    ) -> None:
        """get_by_stock_code() should return the matching product.

        Args:
            session: Async database session fixture.

        Returns:
            None.
        """
        repository = ProductRepository(session)
        created = await repository.create(
            {
                "stock_code": "85123A",
                "description": "WHITE HANGING HEART T-LIGHT HOLDER",
                "last_unit_price": Decimal("2.55"),
            }
        )

        found = await repository.get_by_stock_code("85123A")

        assert isinstance(found, Product)
        assert found.id == created.id
        assert found.last_unit_price == Decimal("2.5500")

    @pytest.mark.anyio
    async def test_get_by_stock_code_returns_none_for_unknown(
        self, session: AsyncSession
    ) -> None:
        """get_by_stock_code() should return None when nothing matches.

        Args:
            session: Async database session fixture.

        Returns:
            None.
        """
        repository = ProductRepository(session)

        assert await repository.get_by_stock_code("NOPE") is None


class TestOrderRepository:
    """Tests for OrderRepository operations."""

    @pytest.fixture
    def anyio_backend(self) -> str:
        """Provide asyncio backend for anyio-marked tests.

        Returns:
            The backend name.
        """
        return "asyncio"

    @pytest.mark.anyio
    async def test_get_by_order_number_returns_order(
        self, session: AsyncSession
    ) -> None:
        """get_by_order_number() should return the matching order.

        Args:
            session: Async database session fixture.

        Returns:
            None.
        """
        repository = OrderRepository(session)
        created = await repository.create(
            {
                "order_number": "536365",
                "ordered_at": datetime(2010, 12, 1, 8, 26, tzinfo=UTC),
            }
        )

        found = await repository.get_by_order_number("536365")

        assert isinstance(found, Order)
        assert found.id == created.id
        assert found.is_cancelled is False

    @pytest.mark.anyio
    async def test_cancelled_order_is_persisted(self, session: AsyncSession) -> None:
        """An order flagged as cancelled should round-trip that flag.

        Args:
            session: Async database session fixture.

        Returns:
            None.
        """
        repository = OrderRepository(session)

        created = await repository.create(
            {
                "order_number": "C536379",
                "ordered_at": datetime(2010, 12, 1, 9, 41, tzinfo=UTC),
                "is_cancelled": True,
            }
        )

        assert created.is_cancelled is True


class TestOrderItemRepository:
    """Tests for OrderItemRepository operations."""

    @pytest.fixture
    def anyio_backend(self) -> str:
        """Provide asyncio backend for anyio-marked tests.

        Returns:
            The backend name.
        """
        return "asyncio"

    @pytest.mark.anyio
    async def test_list_by_order_returns_only_that_orders_lines(
        self, session: AsyncSession
    ) -> None:
        """list_by_order() should return the lines of the requested order only.

        Args:
            session: Async database session fixture.

        Returns:
            None.
        """
        order_repository = OrderRepository(session)
        product_repository = ProductRepository(session)
        repository = OrderItemRepository(session)

        first_order = await order_repository.create(
            {
                "order_number": "536365",
                "ordered_at": datetime(2010, 12, 1, 8, 26, tzinfo=UTC),
            }
        )
        second_order = await order_repository.create(
            {
                "order_number": "536366",
                "ordered_at": datetime(2010, 12, 1, 8, 28, tzinfo=UTC),
            }
        )
        product = await product_repository.create({"stock_code": "85123A"})

        await repository.create(
            {
                "order_id": first_order.id,
                "product_id": product.id,
                "quantity": 6,
                "unit_price": Decimal("2.55"),
                "line_total": Decimal("15.30"),
            }
        )
        await repository.create(
            {
                "order_id": second_order.id,
                "product_id": product.id,
                "quantity": 2,
                "unit_price": Decimal("2.55"),
                "line_total": Decimal("5.10"),
            }
        )

        lines = await repository.list_by_order(first_order.id)

        assert len(lines) == 1
        assert isinstance(lines[0], OrderItem)
        assert lines[0].quantity == 6
        assert lines[0].line_total == Decimal("15.3000")


class TestProductReturnRepository:
    """Tests for ProductReturnRepository operations."""

    @pytest.fixture
    def anyio_backend(self) -> str:
        """Provide asyncio backend for anyio-marked tests.

        Returns:
            The backend name.
        """
        return "asyncio"

    @pytest.mark.anyio
    async def test_get_by_return_order_number_returns_return(
        self, session: AsyncSession
    ) -> None:
        """get_by_return_order_number() should return the matching return.

        Args:
            session: Async database session fixture.

        Returns:
            None.
        """
        product = await ProductRepository(session).create({"stock_code": "22423"})
        repository = ProductReturnRepository(session)

        created = await repository.create(
            {
                "product_id": product.id,
                "return_order_number": "C536379",
                "quantity": 1,
                "amount": Decimal("27.50"),
                "returned_at": datetime(2010, 12, 1, 9, 41, tzinfo=UTC),
            }
        )

        found = await repository.get_by_return_order_number("C536379")

        assert isinstance(found, ProductReturn)
        assert found.id == created.id

    @pytest.mark.anyio
    async def test_return_quantities_are_stored_positive(
        self, session: AsyncSession
    ) -> None:
        """Returns should store magnitude, not the source's negative quantity.

        Args:
            session: Async database session fixture.

        Returns:
            None.
        """
        product = await ProductRepository(session).create({"stock_code": "22960"})
        repository = ProductReturnRepository(session)

        created = await repository.create(
            {
                "product_id": product.id,
                "return_order_number": "C536383",
                "quantity": 3,
                "amount": Decimal("12.75"),
                "returned_at": datetime(2010, 12, 1, 9, 49, tzinfo=UTC),
            }
        )

        assert created.quantity > 0
        assert created.amount > 0
