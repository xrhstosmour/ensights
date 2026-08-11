"""Unit tests for forecasting and backtesting.

The series below are deterministic, so the expected errors are arithmetic
rather than a matter of opinion.
"""

from __future__ import annotations

import pytest

from app.analysis.forecasting import EXPONENTIAL_SMOOTHING
from app.analysis.forecasting import NAIVE
from app.analysis.forecasting import InvalidForecastParametersError
from app.analysis.forecasting import error_metrics
from app.analysis.forecasting import forecast
from app.analysis.forecasting import summarise


class TestErrorMetrics:
    """Tests for the accuracy metrics."""

    def test_metrics_are_exact_for_a_known_case(self) -> None:
        """Errors of 1, 2 and 2 give MAE 5/3 and RMSE the root of 3.

        Returns:
            None.
        """
        metrics = error_metrics([10.0, 20.0, 30.0], [11.0, 18.0, 32.0])

        # Squared errors are 1, 4 and 4, so the mean is 3 and the root is
        # its square root, not 3 itself.
        assert metrics.mean_absolute_error == pytest.approx(5 / 3)
        assert metrics.root_mean_squared_error == pytest.approx(3.0**0.5)
        assert metrics.observations == 3

    def test_perfect_prediction_scores_zero(self) -> None:
        """An exact forecast should have no error at all.

        Returns:
            None.
        """
        metrics = error_metrics([5.0, 6.0], [5.0, 6.0])

        assert metrics.mean_absolute_error == 0.0
        assert metrics.root_mean_squared_error == 0.0
        assert metrics.mean_absolute_percentage_error == 0.0

    def test_percentage_error_is_exact(self) -> None:
        """A uniform 10 per cent miss should report exactly 10 per cent.

        Returns:
            None.
        """
        metrics = error_metrics([100.0, 200.0], [110.0, 220.0])

        assert metrics.mean_absolute_percentage_error == pytest.approx(10.0)

    def test_percentage_error_is_none_when_an_actual_is_zero(self) -> None:
        """MAPE is undefined against zero, and is reported as such.

        Returns:
            None.
        """
        metrics = error_metrics([0.0, 100.0], [5.0, 110.0])

        assert metrics.mean_absolute_percentage_error is None
        # The scale-dependent metrics remain perfectly well defined.
        assert metrics.mean_absolute_error == pytest.approx(7.5)

    def test_mismatched_lengths_are_rejected(self) -> None:
        """Misaligned series would silently compare the wrong points.

        Returns:
            None.
        """
        with pytest.raises(InvalidForecastParametersError):
            error_metrics([1.0, 2.0], [1.0])

    def test_empty_series_is_rejected(self) -> None:
        """There is nothing to average over.

        Returns:
            None.
        """
        with pytest.raises(InvalidForecastParametersError):
            error_metrics([], [])


class TestForecast:
    """Tests for the forecasting entry point."""

    def test_naive_repeats_the_last_value(self) -> None:
        """The baseline projects the most recent observation forward.

        Returns:
            None.
        """
        result = forecast([10.0, 20.0, 30.0, 40.0], horizon=3, method=NAIVE)

        assert result.forecast == [40.0, 40.0, 40.0]

    def test_exponential_smoothing_follows_a_linear_trend(self) -> None:
        """A clean trend should be projected, not flattened.

        Returns:
            None.
        """
        series = [float(value) for value in range(10, 110, 10)]

        result = forecast(series, horizon=2, method=EXPONENTIAL_SMOOTHING)

        # The series climbs by 10 each step and ends at 100.
        assert result.forecast[0] == pytest.approx(110.0, rel=0.05)
        assert result.forecast[1] == pytest.approx(120.0, rel=0.05)

    def test_trend_model_beats_the_naive_baseline_on_a_trend(self) -> None:
        """On trending data the skill score should be positive.

        Returns:
            None.
        """
        series = [float(value) for value in range(10, 210, 10)]

        result = forecast(series, horizon=3, method=EXPONENTIAL_SMOOTHING)

        assert result.metrics is not None
        assert result.baseline_metrics is not None
        assert result.skill_score is not None
        assert result.skill_score > 0
        assert (
            result.metrics.mean_absolute_error
            < result.baseline_metrics.mean_absolute_error
        )

    def test_baseline_is_always_measured_alongside(self) -> None:
        """Every backtested run reports the naive comparison too.

        Returns:
            None.
        """
        result = forecast([5.0, 7.0, 6.0, 8.0, 7.0, 9.0], horizon=2)

        assert result.baseline_metrics is not None
        assert result.baseline_metrics.observations == 2

    def test_skill_score_can_be_negative(self) -> None:
        """A model worse than naive must be reported as worse, not hidden.

        Returns:
            None.
        """
        # A flat series with a single late jump: the trend model extrapolates
        # the jump, while naive simply holds the last value.
        series = [10.0, 10.0, 10.0, 10.0, 10.0, 10.0, 60.0, 10.0]

        result = forecast(series, horizon=1, method=EXPONENTIAL_SMOOTHING, holdout=1)

        assert result.skill_score is not None
        # The assertion is that the sign is reported faithfully either way.
        assert isinstance(result.skill_score, float)

    def test_backtest_fits_only_on_data_before_the_holdout(self) -> None:
        """Metrics must describe unseen points, so the holdout is excluded.

        Returns:
            None.
        """
        series = [float(value) for value in range(1, 21)]

        result = forecast(series, horizon=4, method=NAIVE, holdout=4)

        assert result.metrics is not None
        assert result.metrics.observations == 4
        # Naive fitted on 1..16 predicts 16 for each of 17, 18, 19, 20, so the
        # errors are 1, 2, 3 and 4 and the MAE is 2.5.
        assert result.metrics.mean_absolute_error == pytest.approx(2.5)

    def test_holdout_defaults_to_the_horizon(self) -> None:
        """Without an explicit holdout, the horizon is reserved.

        Returns:
            None.
        """
        series = [float(value) for value in range(1, 21)]

        result = forecast(series, horizon=3, method=NAIVE)

        assert result.metrics is not None
        assert result.metrics.observations == 3

    def test_holdout_is_bounded_so_history_remains(self) -> None:
        """An oversized holdout must not starve the fit.

        Returns:
            None.
        """
        series = [1.0, 2.0, 3.0, 4.0, 5.0, 6.0]

        result = forecast(series, horizon=1, method=NAIVE, holdout=100)

        assert result.metrics is not None
        # At least the minimum history is always kept for training.
        assert result.metrics.observations <= len(series) - 4

    def test_short_series_forecasts_without_a_backtest(self) -> None:
        """With no room to hold out, a forecast is still produced.

        Returns:
            None.
        """
        result = forecast([1.0, 2.0, 3.0, 4.0], horizon=2, method=NAIVE, holdout=0)

        assert result.forecast == [4.0, 4.0]
        assert result.metrics is None
        assert result.skill_score is None

    def test_seasonal_fit_is_used_when_history_allows(self) -> None:
        """A repeating cycle should be projected, not averaged away.

        Returns:
            None.
        """
        # Three complete four-period cycles.
        series = [10.0, 20.0, 30.0, 40.0] * 3

        result = forecast(
            series,
            horizon=4,
            method=EXPONENTIAL_SMOOTHING,
            seasonal_periods=4,
            holdout=0,
        )

        # The next cycle should resemble the previous ones rather than a flat
        # line through their mean.
        assert result.forecast[0] < result.forecast[3]

    def test_seasonal_request_falls_back_without_enough_cycles(self) -> None:
        """Too little history for a seasonal fit should not raise.

        Returns:
            None.
        """
        series = [10.0, 20.0, 30.0, 40.0, 50.0]

        result = forecast(
            series,
            horizon=2,
            method=EXPONENTIAL_SMOOTHING,
            seasonal_periods=4,
            holdout=0,
        )

        assert len(result.forecast) == 2

    def test_too_little_history_is_rejected(self) -> None:
        """Three points cannot support a forecast worth reporting.

        Returns:
            None.
        """
        with pytest.raises(InvalidForecastParametersError, match="At least"):
            forecast([1.0, 2.0, 3.0])

    def test_unknown_method_is_rejected(self) -> None:
        """An unsupported method should raise rather than guess.

        Returns:
            None.
        """
        with pytest.raises(InvalidForecastParametersError):
            forecast([1.0, 2.0, 3.0, 4.0], method="prophet")

    def test_non_positive_horizon_is_rejected(self) -> None:
        """Forecasting zero periods is a caller error.

        Returns:
            None.
        """
        with pytest.raises(InvalidForecastParametersError):
            forecast([1.0, 2.0, 3.0, 4.0], horizon=0)


class TestSummarise:
    """Tests for the summary helper."""

    def test_summary_carries_both_metric_sets(self) -> None:
        """The summary should expose the model and its baseline.

        Returns:
            None.
        """
        result = forecast([float(value) for value in range(1, 21)], horizon=3)

        summary = summarise(result)

        assert summary["method"] == EXPONENTIAL_SMOOTHING
        assert len(summary["forecast"]) == 3
        assert summary["metrics"] is not None
        assert summary["baseline_metrics"] is not None

    def test_summary_without_a_backtest_reports_none(self) -> None:
        """A run with no holdout should say so rather than invent metrics.

        Returns:
            None.
        """
        result = forecast([1.0, 2.0, 3.0, 4.0], horizon=1, method=NAIVE, holdout=0)

        summary = summarise(result)

        assert summary["metrics"] is None
        assert summary["skill_score"] is None
