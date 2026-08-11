"""Response schemas for the forecasting endpoint."""

from __future__ import annotations

from datetime import datetime

from pydantic import Field

from app.schemas.base import BaseSchema


class ErrorMetricsResponse(BaseSchema):
    """Forecast accuracy on held-out observations."""

    mean_absolute_error: float
    root_mean_squared_error: float
    mean_absolute_percentage_error: float | None = Field(
        default=None,
        description=(
            "None when any held-out actual is zero, where the ratio is "
            "undefined. The absolute metrics remain valid."
        ),
    )
    observations: int


class ForecastResponse(BaseSchema):
    """A revenue forecast with its measured accuracy."""

    method: str
    granularity: str
    horizon: int
    history_length: int
    history_periods: list[datetime] = Field(default_factory=list)
    forecast: list[float] = Field(default_factory=list)
    metrics: ErrorMetricsResponse | None = None
    baseline_metrics: ErrorMetricsResponse | None = Field(
        default=None,
        description="Accuracy of a naive last-value forecast on the same holdout.",
    )
    skill_score: float | None = Field(
        default=None,
        description=(
            "Fractional improvement in mean absolute error over the naive "
            "baseline. Negative means the model performed worse than simply "
            "repeating the last observed value."
        ),
    )
