"""Cohort revenue-curve shape classification.

Growth accounting (`app/analysis/growth_accounting.py`) answers whether
revenue is growing overall. This module answers a narrower question from the
same quantitative product-market-fit framework popularised by Tribe Capital:
for one acquisition cohort, does its later spending grow, hold steady, or
decline relative to its own first period?

A cohort's revenue_retention_rate at period_index 0 is always 1.0 by
definition, so the trend is fit from period_index 1 onward. The slope of that
line, in revenue_retention_rate per period, is classified as:

* **super-linear** — positive slope, the cohort spends more over time
* **linear** — slope within a small tolerance of zero, spend holds steady
* **sub-linear** — negative slope, spend declines over time

The framework's authors give no numeric threshold for the tolerance band; it
exists only so that rounding noise around a truly flat curve does not flip
the label back and forth.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING
from typing import Any

from app.core.logging import get_logger

if TYPE_CHECKING:
    from collections.abc import Sequence

logger = get_logger("analysis.cohort_shape")

# A slope inside this band, in revenue_retention_rate per period, is treated
# as flat rather than trending.
FLAT_SLOPE_TOLERANCE = 0.01

SUPER_LINEAR = "super-linear"
LINEAR = "linear"
SUB_LINEAR = "sub-linear"


class CohortShapeError(Exception):
    """Base class for cohort shape classification failures."""


class InsufficientCohortDataError(CohortShapeError):
    """Raised when a cohort has too few periods after acquisition to fit a trend."""


@dataclass
class CohortShapeResult:
    """The trend classification for one cohort's revenue-retention curve.

    Attributes:
        cohort_month: The acquisition cohort this result describes.
        periods: Number of period_index points after 0 used to fit the trend.
        slope: Ordinary-least-squares slope of revenue_retention_rate against
            period_index, restricted to periods after acquisition.
        shape: "super-linear", "linear" or "sub-linear".
    """

    cohort_month: Any
    periods: int
    slope: float
    shape: str


def _slope(points: Sequence[tuple[int, float]]) -> float:
    """Ordinary-least-squares slope of y against x.

    Args:
        points: (x, y) pairs.

    Returns:
        The slope, or zero if every x value is identical.
    """
    count = len(points)
    sum_x = sum(x for x, _ in points)
    sum_y = sum(y for _, y in points)
    sum_xx = sum(x * x for x, _ in points)
    sum_xy = sum(x * y for x, y in points)
    denominator = count * sum_xx - sum_x * sum_x
    if denominator == 0:
        return 0.0
    return (count * sum_xy - sum_x * sum_y) / denominator


def classify(
    cohort_month: Any,  # noqa: ANN401
    revenue_retention: Sequence[tuple[int, float]],
) -> CohortShapeResult:
    """Classify one cohort's revenue-retention curve.

    Args:
        cohort_month: The acquisition cohort this curve belongs to.
        revenue_retention: (period_index, revenue_retention_rate) pairs for
            this cohort, in any order.

    Returns:
        The fitted slope and its shape label.

    Raises:
        InsufficientCohortDataError: If fewer than two periods after
            acquisition are available; a trend needs at least two points.
    """
    later = sorted((index, rate) for index, rate in revenue_retention if index > 0)
    if len(later) < 2:
        message = (
            f"Cohort {cohort_month!r} has {len(later)} period(s) after "
            "acquisition, at least 2 are needed to fit a trend"
        )
        raise InsufficientCohortDataError(message)

    slope = _slope(later)
    if slope > FLAT_SLOPE_TOLERANCE:
        shape = SUPER_LINEAR
    elif slope < -FLAT_SLOPE_TOLERANCE:
        shape = SUB_LINEAR
    else:
        shape = LINEAR

    return CohortShapeResult(
        cohort_month=cohort_month, periods=len(later), slope=slope, shape=shape
    )


def classify_all(rows: Sequence[dict[str, Any]]) -> list[CohortShapeResult]:
    """Classify every cohort in a cohort-retention grid.

    Cohorts with fewer than two periods after acquisition are skipped rather
    than raised on: a recent cohort with no later activity yet is the normal
    case, not an error.

    Args:
        rows: Cohort-retention rows carrying "cohort_month", "period_index"
            and "revenue_retention_rate".

    Returns:
        One result per cohort with enough periods to classify, ordered by
        cohort_month.
    """
    by_cohort: dict[Any, list[tuple[int, float]]] = {}
    for row in rows:
        by_cohort.setdefault(row["cohort_month"], []).append(
            (row["period_index"], row["revenue_retention_rate"])
        )

    results: list[CohortShapeResult] = []
    for cohort_month in sorted(by_cohort):
        try:
            results.append(classify(cohort_month, by_cohort[cohort_month]))
        except InsufficientCohortDataError:
            continue

    logger.info("cohort_shape_classified", cohorts=len(results))
    return results
