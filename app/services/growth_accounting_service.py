"""Growth accounting over the recorded transaction history.

Builds the customer-by-period activity log the decomposition needs, and runs
it. Everything reported is measured from the transaction record: no margin, no
acquisition spend, no assumptions of any kind.
"""

from __future__ import annotations

from typing import TYPE_CHECKING
from typing import Any

from sqlalchemy import Select
from sqlalchemy import func
from sqlalchemy import literal
from sqlalchemy import select
from sqlmodel import col

from app.analysis.growth_accounting import GrowthAccountingError
from app.analysis.growth_accounting import GrowthAccountingResult
from app.analysis.growth_accounting import InvalidActivityError
from app.analysis.growth_accounting import analyse
from app.core.logging import get_logger
from app.core.tenant import get_current_tenant_id
from app.models.customer import Customer
from app.models.order import Order
from app.models.order_item import OrderItem

if TYPE_CHECKING:
    from datetime import datetime

    from sqlalchemy.ext.asyncio import AsyncSession

logger = get_logger("service.growth_accounting")

__all__ = [
    "GrowthAccountingError",
    "GrowthAccountingService",
    "InvalidActivityError",
]

ALLOWED_GRANULARITIES = frozenset({"day", "week", "month", "quarter", "year"})


class GrowthAccountingService:
    """Measures how a merchant's revenue is gained and lost over time."""

    def __init__(self, session: AsyncSession) -> None:
        """Initialise the service.

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

    async def activity(
        self,
        granularity: str = "month",
        start: datetime | None = None,
        end: datetime | None = None,
    ) -> list[dict[str, Any]]:
        """Build the customer-by-period revenue log.

        Anonymous sales are excluded. The decomposition tracks individual
        customers across periods, and a sale that cannot be attributed to one
        would be counted as a new customer every period, inflating both the
        new and churned flows.

        Args:
            granularity: Bucket size for the periods.
            start: Inclusive lower bound on order time.
            end: Exclusive upper bound on order time.

        Returns:
            Rows of customer, period and revenue.

        Raises:
            InvalidActivityError: If the granularity is unsupported.
        """
        if granularity not in ALLOWED_GRANULARITIES:
            message = (
                f"Unsupported granularity {granularity!r}, expected one of "
                f"{', '.join(sorted(ALLOWED_GRANULARITIES))}"
            )
            raise InvalidActivityError(message)

        period = func.date_trunc(literal(granularity), col(Order.ordered_at)).label(
            "period"
        )
        query: Select[Any] = (
            select(
                col(Customer.external_identifier).label("customer"),
                period,
                func.sum(col(OrderItem.line_total)).label("revenue"),
            )
            .join(Order, col(Order.id) == col(OrderItem.order_id))
            .join(Customer, col(Customer.id) == col(Order.customer_id))
            .group_by(col(Customer.external_identifier), period)
            .order_by(period)
        )
        query = self._scope(query, OrderItem, Order, Customer)
        if start is not None:
            query = query.where(col(Order.ordered_at) >= start)
        if end is not None:
            query = query.where(col(Order.ordered_at) < end)

        result = await self.session.execute(query)
        return [
            {
                "customer": row["customer"],
                "period": row["period"],
                "revenue": float(row["revenue"] or 0),
            }
            for row in result.mappings()
        ]

    async def run(
        self,
        granularity: str = "month",
        start: datetime | None = None,
        end: datetime | None = None,
    ) -> GrowthAccountingResult:
        """Decompose revenue change and measure concentration.

        Args:
            granularity: Bucket size for the periods.
            start: Inclusive lower bound on order time.
            end: Exclusive upper bound on order time.

        Returns:
            The per-period flows and the revenue concentration.

        Raises:
            InvalidActivityError: If the activity log is unusable.
        """
        rows = await self.activity(granularity, start, end)
        result = analyse(rows)

        logger.info(
            "growth_accounting_run",
            granularity=granularity,
            periods=len(result.periods),
            customers=result.concentration.customers,
        )
        return result
