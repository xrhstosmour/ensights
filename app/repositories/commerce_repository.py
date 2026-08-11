"""Repositories for the canonical e-commerce entities.

These deliberately stay thin. They cover the lookups that ingestion needs to
stay idempotent, plus bulk insertion; the analytical aggregations live in their
own repository so that import concerns and reporting concerns do not mix.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from sqlmodel import select

from app.models.customer import Customer
from app.models.order import Order
from app.models.order_item import OrderItem
from app.models.product import Product
from app.models.product_return import ProductReturn
from app.models.region import Region
from app.repositories.base import BaseRepository

if TYPE_CHECKING:
    from collections.abc import Sequence

    from sqlalchemy.ext.asyncio import AsyncSession


class RegionRepository(BaseRepository[Region]):
    """Data access for regions."""

    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, Region)

    async def get_by_name(self, name: str) -> Region | None:
        """Fetch a region by its name within the current tenant.

        Args:
            name: Region name as reported by the source.

        Returns:
            The matching region, or None when it does not exist yet.
        """
        query = self._apply_tenant_filter(select(Region).where(Region.name == name))  # type: ignore[arg-type]
        result = await self.session.execute(self._apply_soft_delete_filter(query))
        return result.scalars().first()


class CustomerRepository(BaseRepository[Customer]):
    """Data access for customers."""

    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, Customer)

    async def get_by_external_identifier(self, identifier: str) -> Customer | None:
        """Fetch a customer by the source system's identifier.

        Args:
            identifier: Buyer identifier as reported by the source.

        Returns:
            The matching customer, or None when it does not exist yet.
        """
        query = self._apply_tenant_filter(
            select(Customer).where(Customer.external_identifier == identifier)  # type: ignore[arg-type]
        )
        result = await self.session.execute(self._apply_soft_delete_filter(query))
        return result.scalars().first()


class ProductRepository(BaseRepository[Product]):
    """Data access for products."""

    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, Product)

    async def get_by_stock_code(self, stock_code: str) -> Product | None:
        """Fetch a product by the source system's stock code.

        Args:
            stock_code: Product identifier as reported by the source.

        Returns:
            The matching product, or None when it does not exist yet.
        """
        query = self._apply_tenant_filter(
            select(Product).where(Product.stock_code == stock_code)  # type: ignore[arg-type]
        )
        result = await self.session.execute(self._apply_soft_delete_filter(query))
        return result.scalars().first()


class OrderRepository(BaseRepository[Order]):
    """Data access for orders."""

    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, Order)

    async def get_by_order_number(self, order_number: str) -> Order | None:
        """Fetch an order by the source system's transaction identifier.

        Args:
            order_number: Transaction identifier as reported by the source.

        Returns:
            The matching order, or None when it does not exist yet.
        """
        query = self._apply_tenant_filter(
            select(Order).where(Order.order_number == order_number)  # type: ignore[arg-type]
        )
        result = await self.session.execute(self._apply_soft_delete_filter(query))
        return result.scalars().first()


class OrderItemRepository(BaseRepository[OrderItem]):
    """Data access for order line items."""

    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, OrderItem)

    async def list_by_order(self, order_id: object) -> Sequence[OrderItem]:
        """List the lines belonging to one order.

        Args:
            order_id: Identifier of the owning order.

        Returns:
            The order's line items.
        """
        query = self._apply_tenant_filter(
            select(OrderItem).where(OrderItem.order_id == order_id)  # type: ignore[arg-type]
        )
        result = await self.session.execute(self._apply_soft_delete_filter(query))
        return list(result.scalars().all())


class ProductReturnRepository(BaseRepository[ProductReturn]):
    """Data access for product returns."""

    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, ProductReturn)

    async def get_by_return_order_number(
        self, return_order_number: str
    ) -> ProductReturn | None:
        """Fetch a return by the source system's cancellation identifier.

        Args:
            return_order_number: Cancellation identifier from the source.

        Returns:
            The matching return, or None when it does not exist yet.
        """
        query = self._apply_tenant_filter(
            select(ProductReturn).where(  # type: ignore[arg-type]
                ProductReturn.return_order_number == return_order_number
            )
        )
        result = await self.session.execute(self._apply_soft_delete_filter(query))
        return result.scalars().first()
