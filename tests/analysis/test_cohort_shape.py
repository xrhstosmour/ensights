"""Unit tests for cohort revenue-curve shape classification."""

from __future__ import annotations

import pytest

from app.analysis.cohort_shape import InsufficientCohortDataError
from app.analysis.cohort_shape import classify
from app.analysis.cohort_shape import classify_all


class TestClassify:
    """Tests for classifying a single cohort's curve."""

    def test_growing_spend_is_super_linear(self) -> None:
        """Revenue retention rising over time is a positive signal.

        Returns:
            None.
        """
        result = classify("2024-01", [(0, 1.0), (1, 1.2), (2, 1.5)])

        assert result.shape == "super-linear"
        assert result.slope > 0

    def test_declining_spend_is_sub_linear(self) -> None:
        """Revenue retention falling over time is a negative signal.

        Returns:
            None.
        """
        result = classify("2024-01", [(0, 1.0), (1, 0.5), (2, 0.25)])

        assert result.shape == "sub-linear"
        assert result.slope < 0

    def test_flat_spend_is_linear(self) -> None:
        """A curve that barely moves should not be called a trend.

        Returns:
            None.
        """
        result = classify("2024-01", [(0, 1.0), (1, 0.8), (2, 0.8), (3, 0.8)])

        assert result.shape == "linear"
        assert result.slope == pytest.approx(0.0)

    def test_period_zero_is_excluded_from_the_fit(self) -> None:
        """Period zero is always 1.0 by definition and carries no trend.

        Returns:
            None.
        """
        with_zero = classify("2024-01", [(0, 1.0), (1, 0.5), (2, 0.25)])
        without_zero = classify("2024-01", [(1, 0.5), (2, 0.25)])

        assert with_zero.slope == pytest.approx(without_zero.slope)
        assert with_zero.periods == without_zero.periods == 2

    def test_fewer_than_two_periods_raises(self) -> None:
        """A single point cannot define a trend.

        Returns:
            None.
        """
        with pytest.raises(InsufficientCohortDataError):
            classify("2024-01", [(0, 1.0), (1, 0.5)])


class TestClassifyAll:
    """Tests for classifying a whole cohort-retention grid."""

    def test_each_cohort_is_classified_independently(self) -> None:
        """A growing cohort and a shrinking cohort should not affect each other.

        Returns:
            None.
        """
        rows = [
            {
                "cohort_month": "2024-01",
                "period_index": 0,
                "revenue_retention_rate": 1.0,
            },
            {
                "cohort_month": "2024-01",
                "period_index": 1,
                "revenue_retention_rate": 1.3,
            },
            {
                "cohort_month": "2024-01",
                "period_index": 2,
                "revenue_retention_rate": 1.6,
            },
            {
                "cohort_month": "2024-02",
                "period_index": 0,
                "revenue_retention_rate": 1.0,
            },
            {
                "cohort_month": "2024-02",
                "period_index": 1,
                "revenue_retention_rate": 0.4,
            },
            {
                "cohort_month": "2024-02",
                "period_index": 2,
                "revenue_retention_rate": 0.1,
            },
        ]

        results = {result.cohort_month: result.shape for result in classify_all(rows)}

        assert results["2024-01"] == "super-linear"
        assert results["2024-02"] == "sub-linear"

    def test_young_cohorts_are_skipped_not_raised(self) -> None:
        """A cohort with fewer than two periods after acquisition is too young.

        "2024-01" has two periods after its own month, enough to fit a slope.
        "2024-02" has only one, and "2024-03" has none, neither can be fit.

        Returns:
            None.
        """
        rows = [
            {
                "cohort_month": "2024-01",
                "period_index": 0,
                "revenue_retention_rate": 1.0,
            },
            {
                "cohort_month": "2024-01",
                "period_index": 1,
                "revenue_retention_rate": 0.8,
            },
            {
                "cohort_month": "2024-01",
                "period_index": 2,
                "revenue_retention_rate": 0.6,
            },
            {
                "cohort_month": "2024-02",
                "period_index": 0,
                "revenue_retention_rate": 1.0,
            },
            {
                "cohort_month": "2024-02",
                "period_index": 1,
                "revenue_retention_rate": 0.5,
            },
            {
                "cohort_month": "2024-03",
                "period_index": 0,
                "revenue_retention_rate": 1.0,
            },
        ]

        results = classify_all(rows)

        assert [result.cohort_month for result in results] == ["2024-01"]
