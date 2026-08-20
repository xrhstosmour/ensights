"""Customer and market segmentation via nested clustering.

Builds the two feature sets the tree needs and runs it:

* Level one groups regions by their sales behaviour over time, so the branches
  answer "which markets look alike".
* Level two groups the customers *inside* each of those markets by RFM, so the
  leaves answer "and who are the people in them".

The features are assembled here; the algorithm lives in
`app.analysis.clustering` and knows nothing about the database.
"""

from __future__ import annotations

from typing import TYPE_CHECKING
from typing import Any

from sqlalchemy import Select
from sqlalchemy import func
from sqlalchemy import literal
from sqlalchemy import select
from sqlmodel import col

from app.analysis.clustering import DEFAULT_K_RANGE
from app.analysis.clustering import ClusteringError
from app.analysis.clustering import InvalidClusteringParametersError
from app.analysis.clustering import PartitionResult
from app.analysis.clustering import nested_partition
from app.core.logging import get_logger
from app.core.tenant import get_current_tenant_id
from app.core.tenant import is_system_access
from app.models.order import Order
from app.models.order_item import OrderItem
from app.models.region import Region
from app.repositories.base import TenantContextRequiredError
from app.repositories.business_metrics_repository import BusinessMetricsRepository

if TYPE_CHECKING:
    from collections.abc import Sequence
    from datetime import datetime

    from sqlalchemy.ext.asyncio import AsyncSession

logger = get_logger("service.segmentation")

__all__ = [
    "ClusteringError",
    "InvalidClusteringParametersError",
    "SegmentationService",
]

REGION_FEATURES = ("revenue", "orders", "customers", "active_months")
CUSTOMER_FEATURES = ("recency_days", "frequency", "monetary")


class SegmentationService:
    """Runs the nested region-then-customer segmentation."""

    def __init__(self, session: AsyncSession) -> None:
        """Initialise the service.

        Args:
            session: Async database session.
        """
        self.session = session
        self.metrics = BusinessMetricsRepository(session)

    def _scope(self, query: Select[Any], *models: Any) -> Select[Any]:  # noqa: ANN401
        """Restrict a query to the current tenant and to live rows.

        Args:
            query: Query to constrain.
            *models: Models participating in the query.

        Returns:
            The constrained query.

        Raises:
            TenantContextRequiredError: If no tenant context is set and
                `system_context()` is not active. Running the query
                unfiltered would silently merge every tenant's rows.
        """
        tenant_id = get_current_tenant_id()
        if tenant_id is None and not is_system_access():
            message = (
                "Segmentation query is tenant-scoped, but no tenant "
                "context is set. Set one with tenant_context(...), or wrap "
                "deliberate cross-tenant access in system_context()."
            )
            raise TenantContextRequiredError(message)
        for model in models:
            query = query.where(model.deleted_at.is_(None))
            if tenant_id is not None:
                query = query.where(model.tenant_id == tenant_id)
        return query

    async def region_features(
        self,
        start: datetime | None = None,
        end: datetime | None = None,
    ) -> list[dict[str, Any]]:
        """Build one feature row per region.

        `active_months` is what makes this a region-*and-time* feature set
        rather than a purely spatial one: two regions with equal revenue are
        genuinely different markets if one earned it steadily across the year
        and the other in a single month.

        Args:
            start: Inclusive lower bound on order time.
            end: Exclusive upper bound on order time.

        Returns:
            Feature rows keyed by region name.
        """
        month = func.date_trunc(literal("month"), col(Order.ordered_at))
        query: Select[Any] = (
            select(
                col(Region.name).label("key"),
                func.sum(col(OrderItem.line_total)).label("revenue"),
                func.count(func.distinct(col(Order.id))).label("orders"),
                func.count(func.distinct(col(Order.customer_id))).label("customers"),
                func.count(func.distinct(month)).label("active_months"),
            )
            .join(Order, col(Order.id) == col(OrderItem.order_id))
            .join(Region, col(Region.id) == col(Order.region_id))
            .group_by(col(Region.name))
        )
        query = self._scope(query, OrderItem, Order, Region)
        if start is not None:
            query = query.where(col(Order.ordered_at) >= start)
        if end is not None:
            query = query.where(col(Order.ordered_at) < end)

        result = await self.session.execute(query)
        return [
            {
                "key": row["key"],
                "revenue": float(row["revenue"] or 0),
                "orders": int(row["orders"] or 0),
                "customers": int(row["customers"] or 0),
                "active_months": int(row["active_months"] or 0),
            }
            for row in result.mappings()
        ]

    async def customer_features_by_region(
        self,
        start: datetime | None = None,
        end: datetime | None = None,
    ) -> dict[str, list[dict[str, Any]]]:
        """Build RFM rows for every customer, grouped by their region.

        Args:
            start: Inclusive lower bound on order time.
            end: Exclusive upper bound on order time.

        Returns:
            RFM feature rows keyed by region name.
        """
        rows = await self.metrics.rfm(start=start, end=end)

        grouped: dict[str, list[dict[str, Any]]] = {}
        for row in rows:
            region = row.get("region")
            if region is None:
                # A customer with no region cannot sit under any branch of a
                # region-rooted tree; they are reported by the flat RFM
                # endpoint instead of being forced into an arbitrary group.
                continue
            grouped.setdefault(region, []).append(
                {
                    "key": row["customer_identifier"],
                    "recency_days": float(row["recency_days"] or 0),
                    "frequency": float(row["frequency"] or 0),
                    "monetary": float(row["monetary"] or 0),
                }
            )
        return grouped

    async def run(
        self,
        k_range: Sequence[int] = DEFAULT_K_RANGE,
        start: datetime | None = None,
        end: datetime | None = None,
    ) -> PartitionResult:
        """Build the features and run the nested segmentation.

        Args:
            k_range: Candidate cluster counts to evaluate at both levels.
            start: Inclusive lower bound on order time.
            end: Exclusive upper bound on order time.

        Returns:
            The region clusters, each carrying its customer sub-clusters.

        Raises:
            InvalidClusteringParametersError: If the features are unusable.
        """
        regions = await self.region_features(start, end)
        customers = await self.customer_features_by_region(start, end)

        result = nested_partition(
            regions,
            REGION_FEATURES,
            customers,
            CUSTOMER_FEATURES,
            k_range=k_range,
        )

        logger.info(
            "segmentation_complete",
            regions=len(regions),
            clusters=len(result.clusters),
            silhouette=result.silhouette,
            chosen_k=result.chosen_k,
        )
        return result
