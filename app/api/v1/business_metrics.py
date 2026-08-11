"""Business metrics API routes.

Read-only endpoints for the measured economics: GMV, repeat purchase rate,
cohort retention and RFM. All are authenticated and tenant-scoped.
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
from app.schemas.business_metrics import CohortRetentionRow
from app.schemas.business_metrics import CustomerSummary
from app.schemas.business_metrics import GrossMerchandiseValueRow
from app.schemas.business_metrics import RfmRow
from app.services.business_metrics_service import AnalyticsError
from app.services.business_metrics_service import BusinessMetricsService

router = APIRouter(prefix="/business-metrics", tags=["Business Metrics"])
logger = get_logger("api.business_metrics")

StartQuery = Annotated[
    datetime | None, Query(description="Inclusive start of the reporting window.")
]
EndQuery = Annotated[
    datetime | None, Query(description="Exclusive end of the reporting window.")
]


def _bad_request(error: AnalyticsError) -> HTTPException:
    """Convert a service error into a 400 response.

    Args:
        error: The service-layer failure.

    Returns:
        The HTTP exception to raise.
    """
    return HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(error))


@router.get(
    "/gross-merchandise-value",
    response_model=list[GrossMerchandiseValueRow],
    summary="Gross merchandise value over time",
    description=(
        "Reports GMV per calendar bucket, gross of refunds as is conventional, "
        "with the refunded and net values alongside so neither figure is hidden."
    ),
)
async def gross_merchandise_value(
    session: SessionDependency,
    _current_user: CurrentUser,
    granularity: Annotated[
        str,
        Query(pattern="^(day|week|month|quarter|year)$", description="Bucket size."),
    ] = "month",
    start: StartQuery = None,
    end: EndQuery = None,
) -> list[GrossMerchandiseValueRow]:
    """Report merchandise value over time.

    Args:
        session: Async database session.
        _current_user: Authenticated caller.
        granularity: Bucket size.
        start: Inclusive start of the reporting window.
        end: Exclusive end of the reporting window.

    Returns:
        Period rows, oldest first.

    Raises:
        HTTPException: 400 when the window or granularity is invalid.
    """
    try:
        rows = await BusinessMetricsService(session).gross_merchandise_value(
            granularity, start, end
        )
    except AnalyticsError as error:
        raise _bad_request(error) from error
    return [GrossMerchandiseValueRow.model_validate(row) for row in rows]


@router.get(
    "/customer-summary",
    response_model=CustomerSummary,
    summary="Repeat purchase rate and customer counts",
    description=(
        "Counts identified customers only. Anonymous sales cannot be tied to a "
        "person, and including them would understate repeat behaviour."
    ),
)
async def customer_summary(
    session: SessionDependency,
    _current_user: CurrentUser,
    start: StartQuery = None,
    end: EndQuery = None,
) -> CustomerSummary:
    """Report the repeat purchase rate and the counts behind it.

    Args:
        session: Async database session.
        _current_user: Authenticated caller.
        start: Inclusive start of the reporting window.
        end: Exclusive end of the reporting window.

    Returns:
        Customer counts and averages.

    Raises:
        HTTPException: 400 when the reporting window is invalid.
    """
    try:
        summary = await BusinessMetricsService(session).customer_summary(start, end)
    except AnalyticsError as error:
        raise _bad_request(error) from error
    return CustomerSummary.model_validate(summary)


@router.get(
    "/cohort-retention",
    response_model=list[CohortRetentionRow],
    summary="Monthly acquisition cohorts and their retention",
    description=(
        "Groups customers by the month of their first purchase and counts them "
        "in every later month they bought again."
    ),
)
async def cohort_retention(
    session: SessionDependency,
    _current_user: CurrentUser,
    start: StartQuery = None,
    end: EndQuery = None,
) -> list[CohortRetentionRow]:
    """Report acquisition cohorts and their later activity.

    Args:
        session: Async database session.
        _current_user: Authenticated caller.
        start: Inclusive start of the reporting window.
        end: Exclusive end of the reporting window.

    Returns:
        Cohort grid rows.

    Raises:
        HTTPException: 400 when the reporting window is invalid.
    """
    try:
        rows = await BusinessMetricsService(session).cohort_retention(start, end)
    except AnalyticsError as error:
        raise _bad_request(error) from error
    return [CohortRetentionRow.model_validate(row) for row in rows]


@router.get(
    "/rfm",
    response_model=list[RfmRow],
    summary="Recency, frequency and monetary value per customer",
    description=(
        "The features the customer clustering consumes. The monetary column is "
        "observed value to date, not a predicted lifetime value."
    ),
)
async def rfm(
    session: SessionDependency,
    _current_user: CurrentUser,
    reference: Annotated[
        datetime | None,
        Query(
            description=(
                "Date to measure recency against. Defaults to the latest order "
                "in the data, which keeps historical results reproducible."
            )
        ),
    ] = None,
    start: StartQuery = None,
    end: EndQuery = None,
) -> list[RfmRow]:
    """Report RFM features per customer.

    Args:
        session: Async database session.
        _current_user: Authenticated caller.
        reference: Date to measure recency against.
        start: Inclusive start of the reporting window.
        end: Exclusive end of the reporting window.

    Returns:
        One row per identified customer.

    Raises:
        HTTPException: 400 when the reporting window is invalid.
    """
    try:
        rows = await BusinessMetricsService(session).rfm(reference, start, end)
    except AnalyticsError as error:
        raise _bad_request(error) from error
    return [RfmRow.model_validate(row) for row in rows]
