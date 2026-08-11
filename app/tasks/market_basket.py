"""Market basket analysis background tasks via Celery.

Mining scans every order and, on a full retail history, runs far past any
request's lifetime, so it always executes on a worker.
"""

from __future__ import annotations

from app.celery_app import celery_app
from app.core.logging import get_logger

logger = get_logger("tasks.market_basket")


@celery_app.task(
    bind=True,
    name="app.tasks.market_basket.mine_market_baskets",
    max_retries=1,
    default_retry_delay=60,
)
def mine_market_baskets_task(
    self,
    algorithm: str = "fpgrowth",
    minimum_support: float = 0.01,
    minimum_confidence: float = 0.3,
    maximum_itemset_size: int | None = None,
    start: str | None = None,
    end: str | None = None,
    tenant_id: str | None = None,
) -> dict:
    """Mine the recorded orders and store the resulting rules.

    Args:
        algorithm: Either "apriori" or "fpgrowth".
        minimum_support: Minimum fraction of baskets for an itemset.
        minimum_confidence: Minimum confidence for a rule.
        maximum_itemset_size: Optional cap on itemset size.
        start: Inclusive ISO-8601 start of the window to mine.
        end: Exclusive ISO-8601 end of the window to mine.
        tenant_id: Tenant whose orders should be mined.

    Returns:
        Result dict with the run identifier and counts.
    """
    import asyncio
    from datetime import datetime

    from app.core.tenant import set_current_tenant_id
    from app.database import async_session_factory
    from app.services.market_basket_service import MarketBasketService

    async def _run() -> dict:
        if tenant_id is not None:
            from uuid import UUID

            set_current_tenant_id(UUID(tenant_id))

        async with async_session_factory() as session:
            service = MarketBasketService(session)
            run_identifier, result = await service.run(
                algorithm=algorithm,
                minimum_support=minimum_support,
                minimum_confidence=minimum_confidence,
                maximum_itemset_size=maximum_itemset_size,
                start=datetime.fromisoformat(start) if start else None,
                end=datetime.fromisoformat(end) if end else None,
            )

        return {
            "status": "completed",
            "run_identifier": run_identifier,
            "algorithm": result.algorithm,
            "baskets": result.basket_count,
            "itemsets": len(result.itemsets),
            "rules": len(result.rules),
        }

    return asyncio.run(_run())
