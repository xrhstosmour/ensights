"""Market basket analysis over the recorded orders.

Bridges the pure mining code in `app.analysis.frequent_itemsets` and the
database: builds baskets, runs a mining pass, and persists the run so results
can be read cheaply and repeatedly afterwards.
"""

from __future__ import annotations

from datetime import UTC
from datetime import datetime
from typing import TYPE_CHECKING
from typing import Any
from uuid import uuid4

from sqlalchemy import Select
from sqlalchemy import func
from sqlalchemy import select
from sqlmodel import col

from app.analysis.frequent_itemsets import FPGROWTH
from app.analysis.frequent_itemsets import FrequentItemsetError
from app.analysis.frequent_itemsets import InvalidMiningParametersError
from app.analysis.frequent_itemsets import MiningResult
from app.analysis.frequent_itemsets import mine
from app.core.logging import get_logger
from app.core.tenant import get_current_tenant_id
from app.core.tenant import is_system_access
from app.models.association_rule import AssociationRule
from app.models.association_rule import FrequentItemset
from app.models.order import Order
from app.models.order_item import OrderItem
from app.models.product import Product
from app.repositories.base import TenantContextRequiredError

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

logger = get_logger("service.market_basket")

__all__ = [
    "FrequentItemsetError",
    "InvalidMiningParametersError",
    "MarketBasketService",
]

# Baskets of one item cannot contribute to any co-occurrence, and in retail
# data they are numerous, so excluding them sharpens support values rather
# than distorting them.
MINIMUM_BASKET_SIZE = 2


class MarketBasketService:
    """Runs and stores market basket analyses."""

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

        Raises:
            TenantContextRequiredError: If no tenant context is set and
                `system_context()` is not active. Running the query
                unfiltered would silently merge every tenant's rows.
        """
        tenant_id = get_current_tenant_id()
        if tenant_id is None and not is_system_access():
            message = (
                "Market basket query is tenant-scoped, but no tenant "
                "context is set. Set one with tenant_context(...), or wrap "
                "deliberate cross-tenant access in system_context()."
            )
            raise TenantContextRequiredError(message)
        for model in models:
            query = query.where(model.deleted_at.is_(None))
            if tenant_id is not None:
                query = query.where(model.tenant_id == tenant_id)
        return query

    async def build_baskets(
        self,
        start: datetime | None = None,
        end: datetime | None = None,
        minimum_basket_size: int = MINIMUM_BASKET_SIZE,
    ) -> list[list[str]]:
        """Assemble one basket of stock codes per order.

        Args:
            start: Inclusive lower bound on order time.
            end: Exclusive upper bound on order time.
            minimum_basket_size: Smallest basket worth mining.

        Returns:
            One list of stock codes per qualifying order.
        """
        query: Select[Any] = (
            select(
                col(OrderItem.order_id).label("order_id"),
                col(Product.stock_code).label("stock_code"),
            )
            .join(Product, col(Product.id) == col(OrderItem.product_id))
            .join(Order, col(Order.id) == col(OrderItem.order_id))
        )
        query = self._scope(query, OrderItem, Order, Product)
        if start is not None:
            query = query.where(col(Order.ordered_at) >= start)
        if end is not None:
            query = query.where(col(Order.ordered_at) < end)
        query = query.order_by(col(OrderItem.order_id))

        result = await self.session.execute(query)

        baskets: dict[Any, set[str]] = {}
        for row in result.mappings():
            baskets.setdefault(row["order_id"], set()).add(row["stock_code"])

        return [
            sorted(items)
            for items in baskets.values()
            if len(items) >= minimum_basket_size
        ]

    async def run(
        self,
        algorithm: str = FPGROWTH,
        minimum_support: float = 0.01,
        minimum_confidence: float = 0.3,
        maximum_itemset_size: int | None = None,
        start: datetime | None = None,
        end: datetime | None = None,
        persist: bool = True,
    ) -> tuple[str, MiningResult]:
        """Mine the recorded orders and optionally store the result.

        Args:
            algorithm: Either "apriori" or "fpgrowth".
            minimum_support: Minimum fraction of baskets for an itemset.
            minimum_confidence: Minimum confidence for a rule.
            maximum_itemset_size: Optional cap on itemset size.
            start: Inclusive lower bound on order time.
            end: Exclusive upper bound on order time.
            persist: Whether to write the run to the database.

        Returns:
            The run identifier and the mining result.

        Raises:
            InvalidMiningParametersError: If the parameters are out of range.
        """
        baskets = await self.build_baskets(start, end)
        result = mine(
            baskets,
            algorithm=algorithm,
            minimum_support=minimum_support,
            minimum_confidence=minimum_confidence,
            maximum_itemset_size=maximum_itemset_size,
        )

        run_identifier = uuid4().hex
        if persist:
            await self._persist(run_identifier, result)

        logger.info(
            "market_basket_run",
            run_identifier=run_identifier,
            algorithm=algorithm,
            baskets=result.basket_count,
            itemsets=len(result.itemsets),
            rules=len(result.rules),
            persisted=persist,
        )
        return run_identifier, result

    async def _persist(self, run_identifier: str, result: MiningResult) -> None:
        """Write a completed run to the database.

        Args:
            run_identifier: Identifier grouping this run's rows.
            result: The mining result to store.
        """
        computed_at = datetime.now(UTC)
        tenant_id = get_current_tenant_id()
        descriptions = await self._descriptions(result)

        for itemset in result.itemsets:
            self.session.add(
                FrequentItemset(
                    tenant_id=tenant_id,
                    run_identifier=run_identifier,
                    algorithm=result.algorithm,
                    minimum_support=result.minimum_support,
                    items=list(itemset.items),
                    item_count=len(itemset.items),
                    support=itemset.support,
                    computed_at=computed_at,
                )
            )

        for rule in result.rules:
            self.session.add(
                AssociationRule(
                    tenant_id=tenant_id,
                    run_identifier=run_identifier,
                    algorithm=result.algorithm,
                    antecedents=list(rule.antecedents),
                    consequents=list(rule.consequents),
                    antecedent_descriptions=[
                        descriptions.get(code, code) for code in rule.antecedents
                    ],
                    consequent_descriptions=[
                        descriptions.get(code, code) for code in rule.consequents
                    ],
                    support=rule.support,
                    confidence=rule.confidence,
                    lift=rule.lift,
                    computed_at=computed_at,
                )
            )

        await self.session.commit()

    async def _descriptions(self, result: MiningResult) -> dict[str, str]:
        """Look up product descriptions for the codes a run mentions.

        Rules are unreadable as bare stock codes, and resolving them once at
        write time keeps every later read free of a join.

        Args:
            result: The mining result whose codes need resolving.

        Returns:
            Mapping of stock code to description.
        """
        codes = {
            code
            for rule in result.rules
            for code in (*rule.antecedents, *rule.consequents)
        }
        if not codes:
            return {}

        query: Select[Any] = select(
            col(Product.stock_code), col(Product.description)
        ).where(col(Product.stock_code).in_(codes))
        query = self._scope(query, Product)

        rows = await self.session.execute(query)
        return {
            code: description or code
            for code, description in rows.all()  # noqa: E501
        }

    async def latest_rules(
        self,
        limit: int = 20,
        minimum_lift: float = 1.0,
    ) -> list[dict[str, Any]]:
        """Read the strongest rules from the most recent stored run.

        Args:
            limit: Maximum rules to return.
            minimum_lift: Lowest lift worth reporting. The default of 1.0
                excludes rules no stronger than chance.

        Returns:
            Rule rows ordered by lift, strongest first.
        """
        latest: Select[Any] = select(func.max(col(AssociationRule.computed_at)))
        latest = self._scope(latest, AssociationRule)
        latest_result = await self.session.execute(latest)
        computed_at = latest_result.scalar()

        if computed_at is None:
            return []

        query: Select[Any] = (
            select(AssociationRule)
            .where(col(AssociationRule.computed_at) == computed_at)
            .where(col(AssociationRule.lift) >= minimum_lift)
            .order_by(col(AssociationRule.lift).desc())
            .limit(limit)
        )
        query = self._scope(query, AssociationRule)

        result = await self.session.execute(query)
        return [
            {
                "run_identifier": rule.run_identifier,
                "algorithm": rule.algorithm,
                "antecedents": rule.antecedents,
                "consequents": rule.consequents,
                "antecedent_descriptions": rule.antecedent_descriptions,
                "consequent_descriptions": rule.consequent_descriptions,
                "support": rule.support,
                "confidence": rule.confidence,
                "lift": rule.lift,
                "computed_at": rule.computed_at,
            }
            for rule in result.scalars().all()
        ]
