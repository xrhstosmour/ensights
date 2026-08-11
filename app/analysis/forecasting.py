"""Time series forecasting with honest backtesting.

Forecasts future sales from the recorded history, and, more importantly,
measures how well it does so on data it has not seen.

Every forecast is reported alongside a naive baseline that simply repeats the
last observed value. This is deliberate. A model that cannot beat "tomorrow
looks like today" has demonstrated nothing, and a MAPE quoted without that
comparison is an unfalsifiable number. The skill score reports the improvement
explicitly, and it can be negative.

This module holds no database or framework concerns; it takes a series and
returns forecasts and errors.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from dataclasses import field
from typing import TYPE_CHECKING
from typing import Any

from app.core.logging import get_logger

if TYPE_CHECKING:
    from collections.abc import Sequence
    from datetime import datetime

logger = get_logger("analysis.forecasting")

NAIVE = "naive"
EXPONENTIAL_SMOOTHING = "exponential_smoothing"
METHODS = (NAIVE, EXPONENTIAL_SMOOTHING)

# Holt-Winters needs enough history to estimate level and trend before it can
# say anything; below this it is fitting noise.
MINIMUM_HISTORY = 4


class ForecastError(Exception):
    """Base class for forecasting failures."""


class InvalidForecastParametersError(ForecastError):
    """Raised when the request cannot produce a forecast."""


@dataclass(frozen=True, slots=True)
class ErrorMetrics:
    """Forecast accuracy on held-out observations.

    Attributes:
        mean_absolute_error: Average absolute deviation, in series units
        root_mean_squared_error: Penalises large misses more heavily
        mean_absolute_percentage_error: Scale-free average relative error, or
            None when any actual value is zero and the ratio is undefined
        observations: Number of points the metrics were computed over
    """

    mean_absolute_error: float
    root_mean_squared_error: float
    mean_absolute_percentage_error: float | None
    observations: int


@dataclass
class ForecastResult:
    """A forecast together with its measured accuracy.

    Attributes:
        method: Method used
        horizon: Number of future periods forecast
        forecast: Predicted values, oldest first
        history_length: Number of observations the model was fitted on
        metrics: Accuracy on the holdout, when a backtest was possible
        baseline_metrics: Accuracy of the naive baseline on the same holdout
        skill_score: Fractional improvement in MAE over the baseline; positive
            means the model beat it, negative means it did worse
    """

    method: str
    horizon: int
    forecast: list[float] = field(default_factory=list)
    history_length: int = 0
    metrics: ErrorMetrics | None = None
    baseline_metrics: ErrorMetrics | None = None
    skill_score: float | None = None


def error_metrics(actual: Sequence[float], predicted: Sequence[float]) -> ErrorMetrics:
    """Compute accuracy metrics for a set of predictions.

    Args:
        actual: Observed values.
        predicted: Predicted values, aligned with `actual`.

    Returns:
        The accuracy metrics.

    Raises:
        InvalidForecastParametersError: If the sequences differ in length or
            are empty.
    """
    if len(actual) != len(predicted):
        message = "Actual and predicted series must be the same length"
        raise InvalidForecastParametersError(message)
    if not actual:
        message = "Cannot compute error metrics over an empty series"
        raise InvalidForecastParametersError(message)

    deviations = [abs(a - p) for a, p in zip(actual, predicted, strict=True)]
    squared = [(a - p) ** 2 for a, p in zip(actual, predicted, strict=True)]

    # MAPE is undefined when an actual value is zero. Reporting None is
    # honest; substituting a small number or silently skipping the point
    # would quietly flatter the model.
    percentage: float | None
    if any(a == 0 for a in actual):
        percentage = None
    else:
        percentage = (
            sum(abs((a - p) / a) for a, p in zip(actual, predicted, strict=True))
            / len(actual)
            * 100
        )

    return ErrorMetrics(
        mean_absolute_error=sum(deviations) / len(deviations),
        root_mean_squared_error=math.sqrt(sum(squared) / len(squared)),
        mean_absolute_percentage_error=percentage,
        observations=len(actual),
    )


def _naive_forecast(history: Sequence[float], horizon: int) -> list[float]:
    """Repeat the last observed value across the horizon.

    Args:
        history: Observed series.
        horizon: Number of future periods.

    Returns:
        The baseline forecast.
    """
    return [float(history[-1])] * horizon


def _exponential_smoothing_forecast(
    history: Sequence[float], horizon: int, seasonal_periods: int | None
) -> list[float]:
    """Fit Holt-Winters exponential smoothing and project forward.

    Args:
        history: Observed series.
        horizon: Number of future periods.
        seasonal_periods: Length of the seasonal cycle, when one is expected.

    Returns:
        The forecast values.
    """
    from statsmodels.tsa.holtwinters import ExponentialSmoothing

    values = [float(value) for value in history]

    # A seasonal fit needs at least two complete cycles; asking for one with
    # less history raises inside statsmodels, so fall back to trend only.
    use_seasonal = (
        seasonal_periods is not None
        and seasonal_periods > 1
        and len(values) >= seasonal_periods * 2
    )

    model = ExponentialSmoothing(
        values,
        trend="add",
        seasonal="add" if use_seasonal else None,
        seasonal_periods=seasonal_periods if use_seasonal else None,
        initialization_method="estimated",
    )
    fitted = model.fit(optimized=True)
    return [float(value) for value in fitted.forecast(horizon)]


def _forecast(
    history: Sequence[float],
    horizon: int,
    method: str,
    seasonal_periods: int | None,
) -> list[float]:
    """Dispatch to the requested method.

    Args:
        history: Observed series.
        horizon: Number of future periods.
        method: Method name.
        seasonal_periods: Length of the seasonal cycle.

    Returns:
        The forecast values.
    """
    if method == NAIVE:
        return _naive_forecast(history, horizon)
    return _exponential_smoothing_forecast(history, horizon, seasonal_periods)


def forecast(
    series: Sequence[float],
    horizon: int = 3,
    method: str = EXPONENTIAL_SMOOTHING,
    seasonal_periods: int | None = None,
    holdout: int | None = None,
) -> ForecastResult:
    """Forecast forward and measure accuracy on a held-out tail.

    The backtest fits only on the portion of the series before the holdout, so
    the reported errors describe genuinely unseen data. The final forecast is
    then refitted on the whole series, because there is no reason to discard
    the most recent observations when predicting the future.

    Args:
        series: Observed values, oldest first.
        horizon: Number of future periods to forecast.
        method: Either "naive" or "exponential_smoothing".
        seasonal_periods: Length of the seasonal cycle, when one is expected.
        holdout: Number of trailing observations to reserve for the backtest.
            Defaults to the horizon, bounded so a usable history remains.

    Returns:
        The forecast with its accuracy metrics.

    Raises:
        InvalidForecastParametersError: If the parameters or the series are
            unusable.
    """
    if method not in METHODS:
        message = f"Unknown method {method!r}, expected one of {', '.join(METHODS)}"
        raise InvalidForecastParametersError(message)
    if horizon < 1:
        message = "Horizon must be at least 1"
        raise InvalidForecastParametersError(message)
    if len(series) < MINIMUM_HISTORY:
        message = (
            f"At least {MINIMUM_HISTORY} observations are required to forecast, "
            f"got {len(series)}"
        )
        raise InvalidForecastParametersError(message)

    values = [float(value) for value in series]
    result = ForecastResult(method=method, horizon=horizon, history_length=len(values))

    reserved = holdout if holdout is not None else horizon
    reserved = max(0, min(reserved, len(values) - MINIMUM_HISTORY))

    if reserved > 0:
        training = values[:-reserved]
        actual = values[-reserved:]

        predicted = _forecast(training, reserved, method, seasonal_periods)
        result.metrics = error_metrics(actual, predicted)

        baseline = _naive_forecast(training, reserved)
        result.baseline_metrics = error_metrics(actual, baseline)

        baseline_error = result.baseline_metrics.mean_absolute_error
        if baseline_error > 0:
            result.skill_score = (
                baseline_error - result.metrics.mean_absolute_error
            ) / baseline_error

    result.forecast = _forecast(values, horizon, method, seasonal_periods)

    logger.info(
        "forecast_complete",
        method=method,
        horizon=horizon,
        history=len(values),
        holdout=reserved,
        skill_score=result.skill_score,
    )
    return result


def summarise(
    result: ForecastResult, periods: Sequence[datetime] | None = None
) -> dict[str, Any]:
    """Summarise a forecast for logging or a notebook.

    Args:
        result: The forecast to summarise.
        periods: Optional labels for the forecast periods.

    Returns:
        The forecast values with their accuracy metrics.
    """

    def _metrics(metrics: ErrorMetrics | None) -> dict[str, Any] | None:
        if metrics is None:
            return None
        return {
            "mean_absolute_error": round(metrics.mean_absolute_error, 4),
            "root_mean_squared_error": round(metrics.root_mean_squared_error, 4),
            "mean_absolute_percentage_error": (
                round(metrics.mean_absolute_percentage_error, 4)
                if metrics.mean_absolute_percentage_error is not None
                else None
            ),
            "observations": metrics.observations,
        }

    return {
        "method": result.method,
        "horizon": result.horizon,
        "history_length": result.history_length,
        "forecast": [round(value, 4) for value in result.forecast],
        "periods": [period.isoformat() for period in periods] if periods else None,
        "metrics": _metrics(result.metrics),
        "baseline_metrics": _metrics(result.baseline_metrics),
        "skill_score": (
            round(result.skill_score, 4) if result.skill_score is not None else None
        ),
    }
