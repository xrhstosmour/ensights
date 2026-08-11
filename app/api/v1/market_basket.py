"""Market basket analysis API routes.

Reading stored rules is cheap and open to any authenticated caller. Starting a
mining run is not: it scans every order, so it is dispatched to a worker and
restricted to superusers.
"""

from __future__ import annotations

from datetime import datetime
from typing import Annotated

from fastapi import APIRouter
from fastapi import HTTPException
from fastapi import Query
from fastapi import status

from app.core.logging import get_logger
from app.dependencies import CurrentUser
from app.dependencies import SessionDependency
from app.dependencies import SuperuserUser
from app.schemas.market_basket import AssociationRuleRow
from app.schemas.market_basket import MiningRunAccepted
from app.services.market_basket_service import FrequentItemsetError
from app.services.market_basket_service import MarketBasketService

router = APIRouter(prefix="/market-basket", tags=["Market Basket"])
logger = get_logger("api.market_basket")


@router.get(
    "/rules",
    response_model=list[AssociationRuleRow],
    summary="Association rules from the latest mining run",
    description=(
        "Returns the strongest rules of the most recent stored run. The "
        "default lift floor of 1.0 excludes rules no stronger than chance, "
        "which support and confidence alone would happily promote."
    ),
)
async def association_rules(
    session: SessionDependency,
    _current_user: CurrentUser,
    limit: Annotated[int, Query(ge=1, le=500)] = 20,
    minimum_lift: Annotated[float, Query(ge=0.0)] = 1.0,
) -> list[AssociationRuleRow]:
    """Read the strongest stored association rules.

    Args:
        session: Async database session.
        _current_user: Authenticated caller.
        limit: Maximum rules to return.
        minimum_lift: Lowest lift worth reporting.

    Returns:
        Rule rows, strongest first.
    """
    rows = await MarketBasketService(session).latest_rules(limit, minimum_lift)
    return [AssociationRuleRow.model_validate(row) for row in rows]


@router.post(
    "/runs",
    response_model=MiningRunAccepted,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Start a mining run",
    description=(
        "Queues a market basket analysis. Mining scans every order, so the "
        "work is handed to a background worker rather than held on the request."
    ),
)
async def start_run(
    _superuser: SuperuserUser,
    algorithm: Annotated[str, Query(pattern="^(apriori|fpgrowth)$")] = "fpgrowth",
    minimum_support: Annotated[float, Query(gt=0.0, le=1.0)] = 0.01,
    minimum_confidence: Annotated[float, Query(gt=0.0, le=1.0)] = 0.3,
    maximum_itemset_size: Annotated[int | None, Query(ge=1, le=10)] = None,
    start: Annotated[datetime | None, Query()] = None,
    end: Annotated[datetime | None, Query()] = None,
) -> MiningRunAccepted:
    """Queue a market basket analysis.

    Args:
        _superuser: Authenticated superuser.
        algorithm: Either "apriori" or "fpgrowth".
        minimum_support: Minimum fraction of baskets for an itemset.
        minimum_confidence: Minimum confidence for a rule.
        maximum_itemset_size: Optional cap on itemset size.
        start: Inclusive start of the window to mine.
        end: Exclusive end of the window to mine.

    Returns:
        The queued task's identifier.

    Raises:
        HTTPException: 400 when the parameters are invalid.
    """
    from app.tasks.market_basket import mine_market_baskets_task

    try:
        task = mine_market_baskets_task.delay(
            algorithm=algorithm,
            minimum_support=minimum_support,
            minimum_confidence=minimum_confidence,
            maximum_itemset_size=maximum_itemset_size,
            start=start.isoformat() if start else None,
            end=end.isoformat() if end else None,
            tenant_id=str(_superuser.tenant_id) if _superuser.tenant_id else None,
        )
    except FrequentItemsetError as error:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=str(error)
        ) from error

    return MiningRunAccepted(task_id=str(task.id))
