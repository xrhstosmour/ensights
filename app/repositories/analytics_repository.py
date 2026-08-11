"""Aggregations behind the descriptive analytics.

Kept separate from the commerce repositories on purpose: those exist to make
ingestion idempotent, these exist to answer reporting questions. They share
tables and nothing else.

Every aggregation is expressed in SQL rather than pulled into Python. The
datasets involved run to millions of rows, and the database is where grouping
belongs.
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING
from typing import Any

from sqlalchemy import Select
from sqlalchemy import and_
from sqlalchemy import case
from sqlalchemy import func
from sqlalchemy import literal
from sqlalchemy import select
from sqlmodel import col

from app.core.tenant import get_current_tenant_id
from app.models.customer import Customer
from app.models.order import Order
from app.models.order_item import OrderItem
from app.models.product import Product
from app.models.product_return import ProductReturn
from app.models.region import Region

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

# Price bands, in the dataset's currency units. Open-ended at the top so no
# sale can fall outside the reported bands.
PRICE_BANDS: tuple[tuple[str, Decimal, Decimal | None], ...] = (
    ("0-1", Decimal("0"), Decimal("1")),
    ("1-5", Decimal("1"), Decimal("5")),
    ("5-10", Decimal("5"), Decimal("10")),
    ("10-50", Decimal("10"), Decimal("50")),
    ("50+", Decimal("50"), None),
)

# Rule-based product characteristics.
#
# This dataset carries no structured category, only a free-text description,
# so characteristics are derived by keyword. That is a stated limitation, not
# a modelling preference: the tags are only as good as the vocabulary below,
# and a product matching nothing is reported as "uncategorised" rather than
# being silently dropped. A source that does provide categories should feed
# them through the adapter instead of relying on this.
PRODUCT_CHARACTERISTICS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("christmas", ("CHRISTMAS", "ADVENT", "SANTA", "REINDEER")),
    ("vintage", ("VINTAGE", "RETRO", "ANTIQUE")),
    ("kitchen", ("KITCHEN", "BAKING", "CAKE", "TEA", "MUG", "BOWL", "SPOON", "JAR")),
    ("bag", ("BAG", "LUNCH BOX", "SATCHEL")),
    ("light", ("LIGHT", "LANTERN", "CANDLE", "LAMP", "T-LIGHT")),
    ("decoration", ("DECORATION", "ORNAMENT", "HEART", "GARLAND", "HANGING")),
    ("garden", ("GARDEN", "PLANT", "FLOWER", "SEED")),
    ("stationery", ("CARD", "NOTEBOOK", "PEN", "PENCIL", "WRAP", "PAPER")),
    ("toy", ("TOY", "GAME", "PLAYHOUSE", "DOLL", "PUZZLE")),
)


class AnalyticsRepository:
    """Read-only aggregations over the canonical commerce tables."""

    def __init__(self, session: AsyncSession) -> None:
        """Initialise the repository.

        Args:
            session: Async database session.
        """
        self.session = session

    def _scope(self, query: Select[Any], *models: Any) -> Select[Any]:  # noqa: ANN401
        """Restrict a query to the current tenant and to live rows.

        Args:
            query: Query to constrain.
            *models: Models participating in the query.

        Returns:
            The constrained query.
        """
        tenant_id = get_current_tenant_id()
        for model in models:
            query = query.where(model.deleted_at.is_(None))
            if tenant_id is not None:
                query = query.where(model.tenant_id == tenant_id)
        return query

    def _sales_window(
        self,
        query: Select[Any],
        start: datetime | None,
        end: datetime | None,
    ) -> Select[Any]:
        """Apply an optional reporting window to a sales query.

        Args:
            query: Query to constrain.
            start: Inclusive lower bound on order time.
            end: Exclusive upper bound on order time.

        Returns:
            The constrained query.
        """
        if start is not None:
            query = query.where(col(Order.ordered_at) >= start)
        if end is not None:
            query = query.where(col(Order.ordered_at) < end)
        return query

    async def top_products(
        self,
        limit: int = 10,
        start: datetime | None = None,
        end: datetime | None = None,
    ) -> list[dict[str, Any]]:
        """Rank products by revenue.

        Args:
            limit: Maximum rows to return.
            start: Inclusive lower bound on order time.
            end: Exclusive upper bound on order time.

        Returns:
            Rows of stock code, description, units sold, revenue and orders.
        """
        revenue = func.sum(col(OrderItem.line_total)).label("revenue")
        query: Select[Any] = (
            select(
                col(Product.stock_code).label("stock_code"),
                col(Product.description).label("description"),
                func.sum(col(OrderItem.quantity)).label("units"),
                revenue,
                func.count(func.distinct(col(OrderItem.order_id))).label("orders"),
            )
            .join(Product, col(Product.id) == col(OrderItem.product_id))
            .join(Order, col(Order.id) == col(OrderItem.order_id))
            .group_by(col(Product.stock_code), col(Product.description))
            .order_by(revenue.desc())
            .limit(limit)
        )
        query = self._scope(query, OrderItem, Order, Product)
        query = self._sales_window(query, start, end)

        result = await self.session.execute(query)
        return [dict(row) for row in result.mappings()]

    async def top_customers(
        self,
        limit: int = 10,
        start: datetime | None = None,
        end: datetime | None = None,
    ) -> list[dict[str, Any]]:
        """Rank customers by revenue.

        Anonymous sales are excluded, since they cannot be attributed to a
        buyer. They remain in the product, region and time breakdowns.

        Args:
            limit: Maximum rows to return.
            start: Inclusive lower bound on order time.
            end: Exclusive upper bound on order time.

        Returns:
            Rows of customer identifier, region, orders, units and revenue.
        """
        revenue = func.sum(col(OrderItem.line_total)).label("revenue")
        query: Select[Any] = (
            select(
                col(Customer.external_identifier).label("customer_identifier"),
                col(Region.name).label("region"),
                func.count(func.distinct(col(Order.id))).label("orders"),
                func.sum(col(OrderItem.quantity)).label("units"),
                revenue,
            )
            .join(Order, col(Order.id) == col(OrderItem.order_id))
            .join(Customer, col(Customer.id) == col(Order.customer_id))
            .outerjoin(Region, col(Region.id) == col(Order.region_id))
            .group_by(col(Customer.external_identifier), col(Region.name))
            .order_by(revenue.desc())
            .limit(limit)
        )
        query = self._scope(query, OrderItem, Order, Customer)
        query = self._sales_window(query, start, end)

        result = await self.session.execute(query)
        return [dict(row) for row in result.mappings()]

    async def top_regions(
        self,
        limit: int = 10,
        start: datetime | None = None,
        end: datetime | None = None,
    ) -> list[dict[str, Any]]:
        """Rank regions by revenue.

        Args:
            limit: Maximum rows to return.
            start: Inclusive lower bound on order time.
            end: Exclusive upper bound on order time.

        Returns:
            Rows of region, orders, customers, units and revenue.
        """
        revenue = func.sum(col(OrderItem.line_total)).label("revenue")
        query: Select[Any] = (
            select(
                col(Region.name).label("region"),
                func.count(func.distinct(col(Order.id))).label("orders"),
                func.count(func.distinct(col(Order.customer_id))).label("customers"),
                func.sum(col(OrderItem.quantity)).label("units"),
                revenue,
            )
            .join(Order, col(Order.id) == col(OrderItem.order_id))
            .join(Region, col(Region.id) == col(Order.region_id))
            .group_by(col(Region.name))
            .order_by(revenue.desc())
            .limit(limit)
        )
        query = self._scope(query, OrderItem, Order, Region)
        query = self._sales_window(query, start, end)

        result = await self.session.execute(query)
        return [dict(row) for row in result.mappings()]

    async def sales_over_time(
        self,
        granularity: str = "month",
        start: datetime | None = None,
        end: datetime | None = None,
    ) -> list[dict[str, Any]]:
        """Aggregate revenue over calendar buckets.

        Args:
            granularity: One of "day", "week", "month", "quarter", "year".
            start: Inclusive lower bound on order time.
            end: Exclusive upper bound on order time.

        Returns:
            Rows of period start, orders, units and revenue, oldest first.

        Raises:
            ValueError: If the granularity is not supported.
        """
        allowed = {"day", "week", "month", "quarter", "year"}
        if granularity not in allowed:
            message = (
                f"Unsupported granularity {granularity!r}, "
                f"expected one of {', '.join(sorted(allowed))}"
            )
            raise ValueError(message)

        period = func.date_trunc(literal(granularity), col(Order.ordered_at)).label(
            "period"
        )
        query = (
            select(
                period,
                func.count(func.distinct(col(Order.id))).label("orders"),
                func.sum(col(OrderItem.quantity)).label("units"),
                func.sum(col(OrderItem.line_total)).label("revenue"),
            )
            .join(Order, col(Order.id) == col(OrderItem.order_id))
            .group_by(period)
            .order_by(period)
        )
        query = self._scope(query, OrderItem, Order)
        query = self._sales_window(query, start, end)

        result = await self.session.execute(query)
        return [dict(row) for row in result.mappings()]

    async def sales_by_weekday(
        self,
        start: datetime | None = None,
        end: datetime | None = None,
    ) -> list[dict[str, Any]]:
        """Aggregate revenue by day of week.

        Answers when in the week sales peak, which the calendar buckets in
        `sales_over_time` cannot show.

        Args:
            start: Inclusive lower bound on order time.
            end: Exclusive upper bound on order time.

        Returns:
            Rows of weekday number (0 is Sunday), orders, units and revenue.
        """
        weekday = func.extract("dow", col(Order.ordered_at)).label("weekday")
        query = (
            select(
                weekday,
                func.count(func.distinct(col(Order.id))).label("orders"),
                func.sum(col(OrderItem.quantity)).label("units"),
                func.sum(col(OrderItem.line_total)).label("revenue"),
            )
            .join(Order, col(Order.id) == col(OrderItem.order_id))
            .group_by(weekday)
            .order_by(weekday)
        )
        query = self._scope(query, OrderItem, Order)
        query = self._sales_window(query, start, end)

        result = await self.session.execute(query)
        return [dict(row) for row in result.mappings()]

    async def top_returned_products(
        self,
        limit: int = 10,
        start: datetime | None = None,
        end: datetime | None = None,
    ) -> list[dict[str, Any]]:
        """Rank products by refunded value.

        Args:
            limit: Maximum rows to return.
            start: Inclusive lower bound on return time.
            end: Exclusive upper bound on return time.

        Returns:
            Rows of stock code, description, units and value returned.
        """
        returned_value = func.sum(col(ProductReturn.amount)).label("returned_value")
        query: Select[Any] = (
            select(
                col(Product.stock_code).label("stock_code"),
                col(Product.description).label("description"),
                func.sum(col(ProductReturn.quantity)).label("returned_units"),
                returned_value,
                func.count(col(ProductReturn.id)).label("return_lines"),
            )
            .join(Product, col(Product.id) == col(ProductReturn.product_id))
            .group_by(col(Product.stock_code), col(Product.description))
            .order_by(returned_value.desc())
            .limit(limit)
        )
        query = self._scope(query, ProductReturn, Product)
        if start is not None:
            query = query.where(col(ProductReturn.returned_at) >= start)
        if end is not None:
            query = query.where(col(ProductReturn.returned_at) < end)

        result = await self.session.execute(query)
        return [dict(row) for row in result.mappings()]

    async def sales_by_price_band(
        self,
        start: datetime | None = None,
        end: datetime | None = None,
    ) -> list[dict[str, Any]]:
        """Aggregate revenue by unit-price band.

        Banding is applied to the line's own price, not the product's last
        known price, so a product that moved between bands over time is
        counted where it actually sold.

        Args:
            start: Inclusive lower bound on order time.
            end: Exclusive upper bound on order time.

        Returns:
            Rows of band label, order lines, units and revenue.
        """
        branches: list[tuple[Any, str]] = []
        for label, lower, upper in PRICE_BANDS:
            if upper is None:
                condition = col(OrderItem.unit_price) >= lower
            else:
                condition = and_(
                    col(OrderItem.unit_price) >= lower,
                    col(OrderItem.unit_price) < upper,
                )
            branches.append((condition, label))

        band = case(*branches, else_="unknown").label("band")
        query = (
            select(
                band,
                func.count(col(OrderItem.id)).label("lines"),
                func.sum(col(OrderItem.quantity)).label("units"),
                func.sum(col(OrderItem.line_total)).label("revenue"),
            )
            .join(Order, col(Order.id) == col(OrderItem.order_id))
            .group_by(band)
        )
        query = self._scope(query, OrderItem, Order)
        query = self._sales_window(query, start, end)

        result = await self.session.execute(query)
        rows = {row["band"]: dict(row) for row in result.mappings()}

        # Return the bands in their natural order, including empty ones, so a
        # caller can chart them without reordering or filling gaps.
        ordered: list[dict[str, Any]] = []
        for label, _lower, _upper in PRICE_BANDS:
            ordered.append(
                rows.get(
                    label,
                    {"band": label, "lines": 0, "units": 0, "revenue": Decimal("0")},
                )
            )
        if "unknown" in rows:
            ordered.append(rows["unknown"])
        return ordered

    async def sales_by_characteristic(
        self,
        start: datetime | None = None,
        end: datetime | None = None,
    ) -> list[dict[str, Any]]:
        """Aggregate revenue by rule-based product characteristic.

        See `PRODUCT_CHARACTERISTICS` for how tags are derived and why. A
        product may match several keyword groups; it is attributed to the
        first that matches, so the bands sum to total revenue rather than
        double counting.

        Args:
            start: Inclusive lower bound on order time.
            end: Exclusive upper bound on order time.

        Returns:
            Rows of characteristic, products, units and revenue.
        """
        branches: list[tuple[Any, str]] = []
        for label, keywords in PRODUCT_CHARACTERISTICS:
            match: Any = None
            for keyword in keywords:
                condition = func.upper(
                    func.coalesce(col(Product.description), "")
                ).like(f"%{keyword}%")
                match = condition if match is None else (match | condition)
            branches.append((match, label))

        characteristic = case(*branches, else_="uncategorised").label("characteristic")
        revenue = func.sum(col(OrderItem.line_total)).label("revenue")
        query = (
            select(
                characteristic,
                func.count(func.distinct(col(Product.id))).label("products"),
                func.sum(col(OrderItem.quantity)).label("units"),
                revenue,
            )
            .join(Product, col(Product.id) == col(OrderItem.product_id))
            .join(Order, col(Order.id) == col(OrderItem.order_id))
            .group_by(characteristic)
            .order_by(revenue.desc())
        )
        query = self._scope(query, OrderItem, Order, Product)
        query = self._sales_window(query, start, end)

        result = await self.session.execute(query)
        return [dict(row) for row in result.mappings()]
