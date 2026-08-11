"""Growth accounting API routes.

Reports how revenue is gained and lost, and how concentrated it is. Everything
here is measured from the transaction record, with no assumed costs.
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
from app.schemas.growth_accounting import GrowthAccountingResponse
from app.services.growth_accounting_service import GrowthAccountingError
from app.services.growth_accounting_service import GrowthAccountingService

router = APIRouter(prefix="/growth-accounting", tags=["Growth Accounting"])
logger = get_logger("api.growth_accounting")


@router.get(
    "",
    response_model=GrowthAccountingResponse,
    summary="Revenue decomposition and concentration",
    description=(
        "Splits each period's revenue change into new, resurrected, retained, "
        "expansion, contraction and churned, and derives the quick ratio, net "
        "churn and gross retention from them. Also reports how concentrated "
        "revenue is across customers, which distinguishes a scalable merchant "
        "from one carried by a few large accounts."
    ),
)
async def growth_accounting(
    session: SessionDependency,
    _current_user: CurrentUser,
    granularity: Annotated[
        str, Query(pattern="^(day|week|month|quarter|year)$")
    ] = "month",
    start: Annotated[datetime | None, Query()] = None,
    end: Annotated[datetime | None, Query()] = None,
) -> GrowthAccountingResponse:
    """Decompose revenue change and measure concentration.

    Args:
        session: Async database session.
        _current_user: Authenticated caller.
        granularity: Bucket size for the periods.
        start: Inclusive start of the window.
        end: Exclusive end of the window.

    Returns:
        The per-period flows and the concentration measures.

    Raises:
        HTTPException: 400 when the request cannot be decomposed.
    """
    try:
        result = await GrowthAccountingService(session).run(granularity, start, end)
    except GrowthAccountingError as error:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=str(error)
        ) from error

    return GrowthAccountingResponse.model_validate(
        {
            "granularity": granularity,
            "periods": [
                {
                    "period": flows.period,
                    "revenue": flows.revenue,
                    "previous_revenue": flows.previous_revenue,
                    "new": flows.new,
                    "resurrected": flows.resurrected,
                    "retained": flows.retained,
                    "expansion": flows.expansion,
                    "contraction": flows.contraction,
                    "churned": flows.churned,
                    "gross_retention_rate": flows.gross_retention_rate,
                    "quick_ratio": flows.quick_ratio,
                    "net_churn_rate": flows.net_churn_rate,
                }
                for flows in result.periods
            ],
            "concentration": result.concentration,
        }
    )
