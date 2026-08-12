"""Aggregations behind the business and unit-economics metrics.

Everything here is measured directly from transaction data. Nothing in this
module assumes a cost, a margin or an acquisition spend, because the source
data carries none of those; the scenario layer that does make such assumptions
is kept separate and clearly labelled.
"""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING
from typing import Any

from sqlalchemy import Integer
from sqlalchemy import Numeric
from sqlalchemy import Select
from sqlalchemy import func
from sqlalchemy import literal
from sqlalchemy import select
from sqlmodel import col

from app.core.tenant import get_current_tenant_id
from app.models.customer import Customer
from app.models.order import Order
from app.models.order_item import OrderItem
from app.models.product_return import ProductReturn
from app.models.region import Region

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession


class BusinessMetricsRepository:
    """Read-only business metrics over the canonical commerce tables."""

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

    def _window(
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

    async def gross_merchandise_value(
        self,
        granularity: str = "month",
        start: datetime | None = None,
        end: datetime | None = None,
    ) -> list[dict[str, Any]]:
        """Gross merchandise value per calendar bucket.

        GMV is reported gross of refunds, which is the conventional
        definition, and the refunded value is returned alongside it so the net
        figure is available without a second query and without hiding either
        number.

        Args:
            granularity: One of "day", "week", "month", "quarter", "year".
            start: Inclusive lower bound on order time.
            end: Exclusive upper bound on order time.

        Returns:
            Rows of period, orders, GMV, refunds and net value.

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
        sales_query: Select[Any] = (
            select(
                period,
                func.count(func.distinct(col(Order.id))).label("orders"),
                func.sum(col(OrderItem.line_total)).label("gross_merchandise_value"),
            )
            .join(Order, col(Order.id) == col(OrderItem.order_id))
            .group_by(period)
            .order_by(period)
        )
        sales_query = self._scope(sales_query, OrderItem, Order)
        sales_query = self._window(sales_query, start, end)

        refund_period = func.date_trunc(
            literal(granularity), col(ProductReturn.returned_at)
        ).label("period")
        refund_query: Select[Any] = (
            select(
                refund_period,
                func.sum(col(ProductReturn.amount)).label("refunds"),
            )
            .group_by(refund_period)
            .order_by(refund_period)
        )
        refund_query = self._scope(refund_query, ProductReturn)
        if start is not None:
            refund_query = refund_query.where(col(ProductReturn.returned_at) >= start)
        if end is not None:
            refund_query = refund_query.where(col(ProductReturn.returned_at) < end)

        sales_result = await self.session.execute(sales_query)
        refund_result = await self.session.execute(refund_query)

        refunds = {row["period"]: row["refunds"] for row in refund_result.mappings()}

        rows: list[dict[str, Any]] = []
        for row in sales_result.mappings():
            gross = row["gross_merchandise_value"] or 0
            refunded = refunds.get(row["period"], 0) or 0
            rows.append(
                {
                    "period": row["period"],
                    "orders": row["orders"],
                    "gross_merchandise_value": gross,
                    "refunds": refunded,
                    "net_merchandise_value": gross - refunded,
                }
            )
        return rows

    async def customer_summary(
        self,
        start: datetime | None = None,
        end: datetime | None = None,
    ) -> dict[str, Any]:
        """Headline customer counts, including the repeat purchase rate.

        Only identified buyers are counted. Anonymous sales cannot be tied to
        a person, so including them would understate repeat behaviour.

        Args:
            start: Inclusive lower bound on order time.
            end: Exclusive upper bound on order time.

        Returns:
            Customer, repeat-customer and one-off counts with the repeat rate,
            average orders per customer and average order value.
        """
        orders_per_customer: Select[Any] = (
            select(
                col(Order.customer_id).label("customer_id"),
                func.count(func.distinct(col(Order.id))).label("orders"),
            )
            .where(col(Order.customer_id).is_not(None))
            .group_by(col(Order.customer_id))
        )
        orders_per_customer = self._scope(orders_per_customer, Order)
        orders_per_customer = self._window(orders_per_customer, start, end)
        per_customer = orders_per_customer.subquery()

        summary_query = select(
            func.count().label("customers"),
            func.sum(func.cast(per_customer.c.orders > 1, Integer)).label(
                "repeat_customers"
            ),
            func.sum(per_customer.c.orders).label("orders"),
        ).select_from(per_customer)

        result = await self.session.execute(summary_query)
        row = result.mappings().first()

        customers = int(row["customers"]) if row else 0
        repeat_customers = int(row["repeat_customers"] or 0) if row else 0
        orders = int(row["orders"] or 0) if row else 0

        revenue_query: Select[Any] = select(
            func.sum(col(OrderItem.line_total)).label("revenue"),
            func.count(func.distinct(col(Order.id))).label("orders"),
        ).join(Order, col(Order.id) == col(OrderItem.order_id))
        revenue_query = self._scope(revenue_query, OrderItem, Order)
        revenue_query = self._window(revenue_query, start, end)

        revenue_result = await self.session.execute(revenue_query)
        revenue_row = revenue_result.mappings().first()
        revenue = (revenue_row["revenue"] if revenue_row else None) or 0
        total_orders = int(revenue_row["orders"] or 0) if revenue_row else 0

        return {
            "customers": customers,
            "repeat_customers": repeat_customers,
            "one_time_customers": customers - repeat_customers,
            "repeat_purchase_rate": (
                repeat_customers / customers if customers else 0.0
            ),
            "average_orders_per_customer": (orders / customers if customers else 0.0),
            "average_order_value": (
                float(revenue) / total_orders if total_orders else 0.0
            ),
        }

    async def cohort_retention(
        self,
        start: datetime | None = None,
        end: datetime | None = None,
    ) -> list[dict[str, Any]]:
        """Monthly acquisition cohorts and their activity in later months.

        Customers are grouped by the month of their first purchase, then
        counted in every month they bought again. `period_index` is the number
        of months after acquisition, so 0 is the cohort's own month.

        Args:
            start: Inclusive lower bound on order time.
            end: Exclusive upper bound on order time.

        Returns:
            Rows of cohort month, period index, active customers, cohort
            size, retention rate, period revenue, cohort revenue and revenue
            retention rate.
        """
        month = func.date_trunc(literal("month"), col(Order.ordered_at))

        activity: Select[Any] = (
            select(
                col(Order.customer_id).label("customer_id"),
                month.label("activity_month"),
                func.sum(col(OrderItem.line_total)).label("revenue"),
            )
            .join(OrderItem, col(OrderItem.order_id) == col(Order.id))
            .where(col(Order.customer_id).is_not(None))
            .group_by(col(Order.customer_id), month)
        )
        activity = self._scope(activity, Order, OrderItem)
        activity = self._window(activity, start, end)
        activity_subquery = activity.subquery()

        first_purchase = select(
            activity_subquery.c.customer_id,
            func.min(activity_subquery.c.activity_month).label("cohort_month"),
        ).group_by(activity_subquery.c.customer_id)
        first_subquery = first_purchase.subquery()

        # Whole months between acquisition and activity, computed in SQL so
        # the grid never has to be materialised in Python.
        months_between = func.round(
            func.cast(
                func.extract(
                    "epoch",
                    activity_subquery.c.activity_month - first_subquery.c.cohort_month,
                )
                / literal(2629746.0),
                Numeric,
            )
        ).label("period_index")

        grid = (
            select(
                first_subquery.c.cohort_month.label("cohort_month"),
                months_between,
                func.count(func.distinct(activity_subquery.c.customer_id)).label(
                    "active_customers"
                ),
                func.sum(activity_subquery.c.revenue).label("period_revenue"),
            )
            .select_from(
                activity_subquery.join(
                    first_subquery,
                    activity_subquery.c.customer_id == first_subquery.c.customer_id,
                )
            )
            .group_by(first_subquery.c.cohort_month, months_between)
            .order_by(first_subquery.c.cohort_month, months_between)
        )

        result = await self.session.execute(grid)
        rows = [dict(row) for row in result.mappings()]

        sizes = {
            row["cohort_month"]: row["active_customers"]
            for row in rows
            if int(row["period_index"]) == 0
        }
        # A cohort's own first period is its revenue baseline: how much later
        # periods retain is measured against what that period alone produced.
        baseline_revenue = {
            row["cohort_month"]: row["period_revenue"] or 0
            for row in rows
            if int(row["period_index"]) == 0
        }
        for row in rows:
            row["period_index"] = int(row["period_index"])
            size = sizes.get(row["cohort_month"], 0)
            row["cohort_size"] = size
            row["retention_rate"] = row["active_customers"] / size if size else 0.0
            row["period_revenue"] = row["period_revenue"] or 0
            cohort_revenue = baseline_revenue.get(row["cohort_month"], 0)
            row["cohort_revenue"] = cohort_revenue
            row["revenue_retention_rate"] = (
                float(row["period_revenue"]) / float(cohort_revenue)
                if cohort_revenue
                else 0.0
            )
        return rows

    async def rfm(
        self,
        reference: datetime | None = None,
        start: datetime | None = None,
        end: datetime | None = None,
    ) -> list[dict[str, Any]]:
        """Recency, frequency and monetary value per customer.

        Recency is days since the customer's last purchase, measured against
        `reference`. When no reference is given, the latest order in the data
        is used, which keeps results stable and reproducible rather than
        drifting with the current date, as the dataset is historical.

        The monetary column is the customer's observed value to date. It is
        emphatically not a predicted lifetime value; no model is involved.

        Args:
            reference: Date to measure recency against.
            start: Inclusive lower bound on order time.
            end: Exclusive upper bound on order time.

        Returns:
            Rows of customer identifier, region, recency, frequency, monetary
            value, first and last purchase.
        """
        if reference is None:
            latest_query: Select[Any] = select(func.max(col(Order.ordered_at)))
            latest_query = self._scope(latest_query, Order)
            latest_query = self._window(latest_query, start, end)
            latest_result = await self.session.execute(latest_query)
            reference = latest_result.scalar() or datetime.now(tz=None)

        last_purchase = func.max(col(Order.ordered_at))
        query: Select[Any] = (
            select(
                col(Customer.external_identifier).label("customer_identifier"),
                col(Region.name).label("region"),
                func.count(func.distinct(col(Order.id))).label("frequency"),
                func.sum(col(OrderItem.line_total)).label("monetary"),
                func.min(col(Order.ordered_at)).label("first_purchase"),
                last_purchase.label("last_purchase"),
                # Whole days elapsed, floored rather than rounded: a customer
                # who bought 27 days and 9 hours ago is 27 days stale, not 28.
                func.cast(
                    func.floor(
                        func.extract("epoch", literal(reference) - last_purchase)
                        / literal(86400.0)
                    ),
                    Integer,
                ).label("recency_days"),
            )
            .join(Order, col(Order.id) == col(OrderItem.order_id))
            .join(Customer, col(Customer.id) == col(Order.customer_id))
            .outerjoin(Region, col(Region.id) == col(Order.region_id))
            .group_by(col(Customer.external_identifier), col(Region.name))
            .order_by(func.sum(col(OrderItem.line_total)).desc())
        )
        query = self._scope(query, OrderItem, Order, Customer)
        query = self._window(query, start, end)

        result = await self.session.execute(query)
        return [dict(row) for row in result.mappings()]
