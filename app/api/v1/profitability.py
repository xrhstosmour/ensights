"""Profitability scenario API routes.

These endpoints do not report whether the business is profitable. The source
data contains no cost of goods and no marketing spend, so that question cannot
be answered from it. What they report is what would follow if the caller's
stated assumptions held, and every response says so.
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
from app.schemas.profitability import ProfitabilityProjection
from app.schemas.profitability import SensitivityRow
from app.schemas.profitability import UnitEconomicsResponse
from app.services.forecasting_service import ForecastError
from app.services.profitability_service import ProfitabilityError
from app.services.profitability_service import ProfitabilityService

router = APIRouter(prefix="/profitability", tags=["Profitability"])
logger = get_logger("api.profitability")

MarginQuery = Annotated[
    float,
    Query(gt=0.0, le=1.0, description="Assumed gross margin, as a fraction."),
]
AcquisitionCostQuery = Annotated[
    float, Query(ge=0.0, description="Assumed spend per newly acquired customer.")
]


@router.get(
    "/projection",
    response_model=ProfitabilityProjection,
    summary="Project profitability under stated assumptions",
    description=(
        "Projects gross and net profit across recorded and forecast periods. "
        "This is a scenario, not a measurement: the source data contains no "
        "cost of goods and no marketing spend, so the result follows from the "
        "assumptions supplied here and holds only insofar as they do."
    ),
)
async def projection(
    session: SessionDependency,
    _current_user: CurrentUser,
    gross_margin: MarginQuery = 0.5,
    customer_acquisition_cost: AcquisitionCostQuery = 0.0,
    operating_cost_per_period: Annotated[float, Query(ge=0.0)] = 0.0,
    granularity: Annotated[
        str, Query(pattern="^(day|week|month|quarter|year)$")
    ] = "month",
    horizon: Annotated[int, Query(ge=0, le=24)] = 6,
    start: Annotated[datetime | None, Query()] = None,
    end: Annotated[datetime | None, Query()] = None,
) -> ProfitabilityProjection:
    """Project profitability forward.

    Args:
        session: Async database session.
        _current_user: Authenticated caller.
        gross_margin: Assumed gross margin.
        customer_acquisition_cost: Assumed spend per new customer.
        operating_cost_per_period: Assumed fixed cost per period.
        granularity: Bucket size for the series.
        horizon: Number of forecast periods to append.
        start: Inclusive start of the history to use.
        end: Exclusive end of the history to use.

    Returns:
        The projection with its assumptions and disclaimer.

    Raises:
        HTTPException: 400 when the assumptions are invalid or there is too
            little history to forecast.
    """
    try:
        result = await ProfitabilityService(session).project_forward(
            gross_margin=gross_margin,
            customer_acquisition_cost=customer_acquisition_cost,
            operating_cost_per_period=operating_cost_per_period,
            granularity=granularity,
            horizon=horizon,
            start=start,
            end=end,
        )
    except (ProfitabilityError, ForecastError) as error:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=str(error)
        ) from error

    return ProfitabilityProjection.model_validate(result)


@router.get(
    "/unit-economics",
    response_model=UnitEconomicsResponse,
    summary="Per-customer economics under stated assumptions",
    description=(
        "Combines observed revenue per customer with an assumed margin and "
        "acquisition cost to derive lifetime value, the LTV:CAC ratio and a "
        "payback period, reported against published benchmarks."
    ),
)
async def customer_unit_economics(
    session: SessionDependency,
    _current_user: CurrentUser,
    gross_margin: MarginQuery = 0.5,
    customer_acquisition_cost: AcquisitionCostQuery = 0.0,
    start: Annotated[datetime | None, Query()] = None,
    end: Annotated[datetime | None, Query()] = None,
) -> UnitEconomicsResponse:
    """Derive per-customer economics.

    Args:
        session: Async database session.
        _current_user: Authenticated caller.
        gross_margin: Assumed gross margin.
        customer_acquisition_cost: Assumed spend per new customer.
        start: Inclusive start of the history to use.
        end: Exclusive end of the history to use.

    Returns:
        The economics with their assumptions and disclaimer.

    Raises:
        HTTPException: 400 when the assumptions are invalid.
    """
    try:
        result = await ProfitabilityService(session).unit_economics(
            gross_margin=gross_margin,
            customer_acquisition_cost=customer_acquisition_cost,
            start=start,
            end=end,
        )
    except ProfitabilityError as error:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=str(error)
        ) from error

    return UnitEconomicsResponse.model_validate(result)


@router.get(
    "/sensitivity",
    response_model=list[SensitivityRow],
    summary="Unit economics across a grid of assumptions",
    description=(
        "Evaluates the same observed data under several margins and "
        "acquisition costs. A single scenario invites being read as a "
        "prediction; the grid makes the dependence on the assumptions visible, "
        "which is the point of presenting this as sensitivity analysis."
    ),
)
async def sensitivity(
    session: SessionDependency,
    _current_user: CurrentUser,
    gross_margins: Annotated[list[float], Query()] = [0.2, 0.4, 0.6],  # noqa: B006
    acquisition_costs: Annotated[list[float], Query()] = [10.0, 25.0, 50.0],  # noqa: B006
    start: Annotated[datetime | None, Query()] = None,
    end: Annotated[datetime | None, Query()] = None,
) -> list[SensitivityRow]:
    """Evaluate unit economics across an assumption grid.

    Args:
        session: Async database session.
        _current_user: Authenticated caller.
        gross_margins: Margin values to evaluate.
        acquisition_costs: Acquisition cost values to evaluate.
        start: Inclusive start of the history to use.
        end: Exclusive end of the history to use.

    Returns:
        One row per combination, each with its own disclaimer.

    Raises:
        HTTPException: 400 when a combination is invalid.
    """
    try:
        rows = await ProfitabilityService(session).sensitivity(
            gross_margins=gross_margins,
            acquisition_costs=acquisition_costs,
            start=start,
            end=end,
        )
    except ProfitabilityError as error:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=str(error)
        ) from error

    return [SensitivityRow.model_validate(row) for row in rows]
