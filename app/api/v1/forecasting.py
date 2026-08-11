"""Sales forecasting API routes."""

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
from app.schemas.forecasting import ForecastResponse
from app.services.forecasting_service import ForecastError
from app.services.forecasting_service import ForecastingService

router = APIRouter(prefix="/forecasting", tags=["Forecasting"])
logger = get_logger("api.forecasting")


@router.get(
    "/revenue",
    response_model=ForecastResponse,
    summary="Forecast revenue",
    description=(
        "Forecasts net revenue forward and reports its accuracy on held-out "
        "history, alongside a naive last-value baseline. A model that cannot "
        "beat that baseline has demonstrated nothing, so the comparison is "
        "always returned."
    ),
)
async def forecast_revenue(
    session: SessionDependency,
    _current_user: CurrentUser,
    granularity: Annotated[
        str, Query(pattern="^(day|week|month|quarter|year)$")
    ] = "month",
    horizon: Annotated[int, Query(ge=1, le=24)] = 3,
    method: Annotated[
        str, Query(pattern="^(naive|exponential_smoothing)$")
    ] = "exponential_smoothing",
    seasonal: Annotated[bool, Query()] = True,
    start: Annotated[datetime | None, Query()] = None,
    end: Annotated[datetime | None, Query()] = None,
) -> ForecastResponse:
    """Forecast revenue over the requested horizon.

    Args:
        session: Async database session.
        _current_user: Authenticated caller.
        granularity: Bucket size for the series.
        horizon: Number of future periods to forecast.
        method: Forecasting method.
        seasonal: Whether to attempt a seasonal fit.
        start: Inclusive start of the history to fit on.
        end: Exclusive end of the history to fit on.

    Returns:
        The forecast with its accuracy metrics.

    Raises:
        HTTPException: 400 when the series cannot be forecast, for example
            when there is too little history.
    """
    try:
        periods, result = await ForecastingService(session).forecast_revenue(
            granularity=granularity,
            horizon=horizon,
            method=method,
            seasonal=seasonal,
            start=start,
            end=end,
        )
    except ForecastError as error:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=str(error)
        ) from error

    return ForecastResponse.model_validate(
        {
            "method": result.method,
            "granularity": granularity,
            "horizon": result.horizon,
            "history_length": result.history_length,
            "history_periods": periods,
            "forecast": result.forecast,
            "metrics": result.metrics,
            "baseline_metrics": result.baseline_metrics,
            "skill_score": result.skill_score,
        }
    )
