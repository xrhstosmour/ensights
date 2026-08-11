"""Response schemas for the descriptive analytics endpoints."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from pydantic import Field

from app.schemas.base import BaseSchema


class TopProductRow(BaseSchema):
    """One product in the revenue ranking."""

    stock_code: str
    description: str | None = None
    units: int = 0
    revenue: Decimal = Decimal("0")
    orders: int = 0


class TopCustomerRow(BaseSchema):
    """One customer in the revenue ranking."""

    customer_identifier: str
    region: str | None = None
    orders: int = 0
    units: int = 0
    revenue: Decimal = Decimal("0")


class TopRegionRow(BaseSchema):
    """One region in the revenue ranking."""

    region: str
    orders: int = 0
    customers: int = 0
    units: int = 0
    revenue: Decimal = Decimal("0")


class SalesPeriodRow(BaseSchema):
    """Revenue within one calendar bucket."""

    period: datetime
    orders: int = 0
    units: int = 0
    revenue: Decimal = Decimal("0")


class SalesWeekdayRow(BaseSchema):
    """Revenue on one day of the week."""

    weekday: int = Field(description="0 is Sunday, following PostgreSQL's dow.")
    orders: int = 0
    units: int = 0
    revenue: Decimal = Decimal("0")


class ReturnedProductRow(BaseSchema):
    """One product in the refund ranking."""

    stock_code: str
    description: str | None = None
    returned_units: int = 0
    returned_value: Decimal = Decimal("0")
    return_lines: int = 0


class PriceBandRow(BaseSchema):
    """Revenue within one unit-price band."""

    band: str
    lines: int = 0
    units: int = 0
    revenue: Decimal = Decimal("0")


class CharacteristicRow(BaseSchema):
    """Revenue attributed to one rule-based product characteristic."""

    characteristic: str
    products: int = 0
    units: int = 0
    revenue: Decimal = Decimal("0")
