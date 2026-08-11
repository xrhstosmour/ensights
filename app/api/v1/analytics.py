"""Descriptive analytics API routes.

Read-only endpoints answering the seven questions in
`documents/roadmap.md`. All are authenticated and tenant-scoped.
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
from app.schemas.analytics import CharacteristicRow
from app.schemas.analytics import PriceBandRow
from app.schemas.analytics import ReturnedProductRow
from app.schemas.analytics import SalesPeriodRow
from app.schemas.analytics import SalesWeekdayRow
from app.schemas.analytics import TopCustomerRow
from app.schemas.analytics import TopProductRow
from app.schemas.analytics import TopRegionRow
from app.services.analytics_service import AnalyticsError
from app.services.analytics_service import AnalyticsService

router = APIRouter(prefix="/analytics", tags=["Analytics"])
logger = get_logger("api.analytics")

LimitQuery = Annotated[int, Query(ge=1, le=200, description="Maximum rows to return.")]
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
    "/top-products",
    response_model=list[TopProductRow],
    summary="Products with the highest sales",
    description="Ranks products by revenue over an optional reporting window.",
)
async def top_products(
    session: SessionDependency,
    _current_user: CurrentUser,
    limit: LimitQuery = 10,
    start: StartQuery = None,
    end: EndQuery = None,
) -> list[TopProductRow]:
    """Rank products by revenue.

    Args:
        session: Async database session.
        _current_user: Authenticated caller.
        limit: Maximum rows to return.
        start: Inclusive start of the reporting window.
        end: Exclusive end of the reporting window.

    Returns:
        Ranked product rows.

    Raises:
        HTTPException: 400 when the reporting window is invalid.
    """
    try:
        rows = await AnalyticsService(session).top_products(limit, start, end)
    except AnalyticsError as error:
        raise _bad_request(error) from error
    return [TopProductRow.model_validate(row) for row in rows]


@router.get(
    "/top-customers",
    response_model=list[TopCustomerRow],
    summary="Customers with the most purchases",
    description=(
        "Ranks customers by revenue. Anonymous sales are excluded, since they "
        "cannot be attributed to a buyer."
    ),
)
async def top_customers(
    session: SessionDependency,
    _current_user: CurrentUser,
    limit: LimitQuery = 10,
    start: StartQuery = None,
    end: EndQuery = None,
) -> list[TopCustomerRow]:
    """Rank customers by revenue.

    Args:
        session: Async database session.
        _current_user: Authenticated caller.
        limit: Maximum rows to return.
        start: Inclusive start of the reporting window.
        end: Exclusive end of the reporting window.

    Returns:
        Ranked customer rows.

    Raises:
        HTTPException: 400 when the reporting window is invalid.
    """
    try:
        rows = await AnalyticsService(session).top_customers(limit, start, end)
    except AnalyticsError as error:
        raise _bad_request(error) from error
    return [TopCustomerRow.model_validate(row) for row in rows]


@router.get(
    "/top-regions",
    response_model=list[TopRegionRow],
    summary="Regions with the most sales",
    description="Ranks regions by revenue over an optional reporting window.",
)
async def top_regions(
    session: SessionDependency,
    _current_user: CurrentUser,
    limit: LimitQuery = 10,
    start: StartQuery = None,
    end: EndQuery = None,
) -> list[TopRegionRow]:
    """Rank regions by revenue.

    Args:
        session: Async database session.
        _current_user: Authenticated caller.
        limit: Maximum rows to return.
        start: Inclusive start of the reporting window.
        end: Exclusive end of the reporting window.

    Returns:
        Ranked region rows.

    Raises:
        HTTPException: 400 when the reporting window is invalid.
    """
    try:
        rows = await AnalyticsService(session).top_regions(limit, start, end)
    except AnalyticsError as error:
        raise _bad_request(error) from error
    return [TopRegionRow.model_validate(row) for row in rows]


@router.get(
    "/sales-over-time",
    response_model=list[SalesPeriodRow],
    summary="When sales happen",
    description="Aggregates revenue into calendar buckets, oldest first.",
)
async def sales_over_time(
    session: SessionDependency,
    _current_user: CurrentUser,
    granularity: Annotated[
        str,
        Query(pattern="^(day|week|month|quarter|year)$", description="Bucket size."),
    ] = "month",
    start: StartQuery = None,
    end: EndQuery = None,
) -> list[SalesPeriodRow]:
    """Aggregate revenue over calendar buckets.

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
        rows = await AnalyticsService(session).sales_over_time(granularity, start, end)
    except AnalyticsError as error:
        raise _bad_request(error) from error
    return [SalesPeriodRow.model_validate(row) for row in rows]


@router.get(
    "/sales-by-weekday",
    response_model=list[SalesWeekdayRow],
    summary="Which weekdays sell most",
    description="Aggregates revenue by day of week, where 0 is Sunday.",
)
async def sales_by_weekday(
    session: SessionDependency,
    _current_user: CurrentUser,
    start: StartQuery = None,
    end: EndQuery = None,
) -> list[SalesWeekdayRow]:
    """Aggregate revenue by day of week.

    Args:
        session: Async database session.
        _current_user: Authenticated caller.
        start: Inclusive start of the reporting window.
        end: Exclusive end of the reporting window.

    Returns:
        Weekday rows, Sunday first.

    Raises:
        HTTPException: 400 when the reporting window is invalid.
    """
    try:
        rows = await AnalyticsService(session).sales_by_weekday(start, end)
    except AnalyticsError as error:
        raise _bad_request(error) from error
    return [SalesWeekdayRow.model_validate(row) for row in rows]


@router.get(
    "/top-returned-products",
    response_model=list[ReturnedProductRow],
    summary="Products with the most refunds",
    description="Ranks products by refunded value over an optional window.",
)
async def top_returned_products(
    session: SessionDependency,
    _current_user: CurrentUser,
    limit: LimitQuery = 10,
    start: StartQuery = None,
    end: EndQuery = None,
) -> list[ReturnedProductRow]:
    """Rank products by refunded value.

    Args:
        session: Async database session.
        _current_user: Authenticated caller.
        limit: Maximum rows to return.
        start: Inclusive start of the reporting window.
        end: Exclusive end of the reporting window.

    Returns:
        Ranked refund rows.

    Raises:
        HTTPException: 400 when the reporting window is invalid.
    """
    try:
        rows = await AnalyticsService(session).top_returned_products(limit, start, end)
    except AnalyticsError as error:
        raise _bad_request(error) from error
    return [ReturnedProductRow.model_validate(row) for row in rows]


@router.get(
    "/sales-by-price-band",
    response_model=list[PriceBandRow],
    summary="Sales per price range",
    description=(
        "Splits revenue across unit-price bands, using the price actually "
        "charged on each line."
    ),
)
async def sales_by_price_band(
    session: SessionDependency,
    _current_user: CurrentUser,
    start: StartQuery = None,
    end: EndQuery = None,
) -> list[PriceBandRow]:
    """Split revenue across unit-price bands.

    Args:
        session: Async database session.
        _current_user: Authenticated caller.
        start: Inclusive start of the reporting window.
        end: Exclusive end of the reporting window.

    Returns:
        One row per band, in ascending price order.

    Raises:
        HTTPException: 400 when the reporting window is invalid.
    """
    try:
        rows = await AnalyticsService(session).sales_by_price_band(start, end)
    except AnalyticsError as error:
        raise _bad_request(error) from error
    return [PriceBandRow.model_validate(row) for row in rows]


@router.get(
    "/sales-by-characteristic",
    response_model=list[CharacteristicRow],
    summary="Sales per product characteristic",
    description=(
        "Splits revenue across keyword-derived product characteristics. This "
        "dataset carries no structured category, so the tags are indicative "
        "rather than authoritative."
    ),
)
async def sales_by_characteristic(
    session: SessionDependency,
    _current_user: CurrentUser,
    start: StartQuery = None,
    end: EndQuery = None,
) -> list[CharacteristicRow]:
    """Split revenue across rule-based product characteristics.

    Args:
        session: Async database session.
        _current_user: Authenticated caller.
        start: Inclusive start of the reporting window.
        end: Exclusive end of the reporting window.

    Returns:
        One row per characteristic, highest revenue first.

    Raises:
        HTTPException: 400 when the reporting window is invalid.
    """
    try:
        rows = await AnalyticsService(session).sales_by_characteristic(start, end)
    except AnalyticsError as error:
        raise _bad_request(error) from error
    return [CharacteristicRow.model_validate(row) for row in rows]
