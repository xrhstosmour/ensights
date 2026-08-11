"""Unit tests for growth accounting and concentration.

The decomposition is only trustworthy if it balances, so the accounting
identities are asserted directly rather than inferred from spot checks.
"""

from __future__ import annotations

import pytest

from app.analysis.growth_accounting import InvalidActivityError
from app.analysis.growth_accounting import analyse
from app.analysis.growth_accounting import concentration
from app.analysis.growth_accounting import decompose
from app.analysis.growth_accounting import summarise


def _activity() -> list[dict[str, object]]:
    """Build a hand-checkable three-period activity log.

    Period 1: A=100, B=50            (both new)
    Period 2: A=150, C=80            (A expands 50, B churns 50, C new 80)
    Period 3: A=150, B=20            (B resurrects 20, C churns 80)

    Returns:
        Activity rows.
    """
    return [
        {"customer": "A", "period": 1, "revenue": 100.0},
        {"customer": "B", "period": 1, "revenue": 50.0},
        {"customer": "A", "period": 2, "revenue": 150.0},
        {"customer": "C", "period": 2, "revenue": 80.0},
        {"customer": "A", "period": 3, "revenue": 150.0},
        {"customer": "B", "period": 3, "revenue": 20.0},
    ]


class TestDecompose:
    """Tests for the six-flow revenue decomposition."""

    def test_first_period_is_all_new(self) -> None:
        """With no history, every customer is a new one.

        Returns:
            None.
        """
        flows = decompose(_activity())

        assert flows[0].new == pytest.approx(150.0)
        assert flows[0].retained == 0.0
        assert flows[0].churned == 0.0
        assert flows[0].previous_revenue == 0.0

    def test_expansion_and_churn_are_separated(self) -> None:
        """A grows by 50 while B leaves with 50; both are recorded.

        Returns:
            None.
        """
        flows = decompose(_activity())

        second = flows[1]
        assert second.retained == pytest.approx(100.0)
        assert second.expansion == pytest.approx(50.0)
        assert second.churned == pytest.approx(50.0)
        assert second.new == pytest.approx(80.0)
        assert second.resurrected == 0.0

    def test_resurrection_is_distinguished_from_new(self) -> None:
        """B returns after a dormant period, so it is not new again.

        Returns:
            None.
        """
        flows = decompose(_activity())

        third = flows[2]
        assert third.resurrected == pytest.approx(20.0)
        assert third.new == 0.0
        assert third.churned == pytest.approx(80.0)

    def test_contraction_is_recorded(self) -> None:
        """A customer who spends less is contraction, not churn.

        Returns:
            None.
        """
        flows = decompose(
            [
                {"customer": "A", "period": 1, "revenue": 100.0},
                {"customer": "A", "period": 2, "revenue": 60.0},
            ]
        )

        assert flows[1].contraction == pytest.approx(40.0)
        assert flows[1].retained == pytest.approx(60.0)
        assert flows[1].churned == 0.0

    def test_current_revenue_identity_holds(self) -> None:
        """revenue(t) must equal retained plus expansion plus new plus resurrected.

        Returns:
            None.
        """
        for flows in decompose(_activity()):
            assert flows.revenue == pytest.approx(
                flows.retained + flows.expansion + flows.new + flows.resurrected
            )

    def test_previous_revenue_identity_holds(self) -> None:
        """revenue(t-1) must equal retained plus contraction plus churned.

        Returns:
            None.
        """
        for flows in decompose(_activity()):
            assert flows.previous_revenue == pytest.approx(
                flows.retained + flows.contraction + flows.churned
            )

    def test_growth_identity_holds(self) -> None:
        """The change in revenue must equal gains minus losses.

        Returns:
            None.
        """
        for flows in decompose(_activity()):
            gains = flows.new + flows.resurrected + flows.expansion
            losses = flows.churned + flows.contraction
            assert flows.revenue - flows.previous_revenue == pytest.approx(
                gains - losses
            )

    def test_quick_ratio_is_exact(self) -> None:
        """Quick ratio is gains over losses.

        Returns:
            None.
        """
        flows = decompose(_activity())

        # Period 2 gains 80 new plus 50 expansion, and loses 50 churned.
        assert flows[1].quick_ratio == pytest.approx(130.0 / 50.0)

    def test_quick_ratio_below_one_means_shrinking(self) -> None:
        """A shrinking period must report a ratio under one.

        Returns:
            None.
        """
        flows = decompose(
            [
                {"customer": "A", "period": 1, "revenue": 100.0},
                {"customer": "B", "period": 1, "revenue": 100.0},
                {"customer": "A", "period": 2, "revenue": 50.0},
            ]
        )

        assert flows[1].quick_ratio is not None
        assert flows[1].quick_ratio < 1.0
        assert flows[1].revenue < flows[1].previous_revenue

    def test_gross_retention_rate_is_exact(self) -> None:
        """Gross retention is retained over previous revenue.

        Returns:
            None.
        """
        flows = decompose(_activity())

        # Period 2 retains 100 of the previous 150.
        assert flows[1].gross_retention_rate == pytest.approx(100.0 / 150.0)

    def test_negative_net_churn_signals_expansion_led_growth(self) -> None:
        """Expansion outpacing losses gives negative net churn.

        Returns:
            None.
        """
        flows = decompose(
            [
                {"customer": "A", "period": 1, "revenue": 100.0},
                {"customer": "A", "period": 2, "revenue": 200.0},
            ]
        )

        assert flows[1].net_churn_rate is not None
        assert flows[1].net_churn_rate < 0

    def test_rates_are_none_for_the_first_period(self) -> None:
        """With no prior revenue the rates are undefined, not zero.

        Returns:
            None.
        """
        flows = decompose(_activity())

        assert flows[0].gross_retention_rate is None
        assert flows[0].net_churn_rate is None

    def test_repeated_rows_for_a_customer_are_summed(self) -> None:
        """Several orders in one period form that customer's period revenue.

        Returns:
            None.
        """
        flows = decompose(
            [
                {"customer": "A", "period": 1, "revenue": 40.0},
                {"customer": "A", "period": 1, "revenue": 60.0},
            ]
        )

        assert flows[0].revenue == pytest.approx(100.0)
        assert flows[0].new == pytest.approx(100.0)

    def test_periods_are_ordered_oldest_first(self) -> None:
        """Out-of-order input must not scramble the decomposition.

        Returns:
            None.
        """
        rows = list(reversed(_activity()))

        flows = decompose(rows)

        assert [flow.period for flow in flows] == [1, 2, 3]

    def test_empty_activity_returns_nothing(self) -> None:
        """No activity should return cleanly rather than raise.

        Returns:
            None.
        """
        assert decompose([]) == []

    def test_missing_field_is_rejected(self) -> None:
        """A malformed row should raise a clear error.

        Returns:
            None.
        """
        with pytest.raises(InvalidActivityError, match="revenue"):
            decompose([{"customer": "A", "period": 1}])

    def test_non_numeric_revenue_is_rejected(self) -> None:
        """A non-numeric revenue should raise here, not later.

        Returns:
            None.
        """
        with pytest.raises(InvalidActivityError, match="not numeric"):
            decompose([{"customer": "A", "period": 1, "revenue": "lots"}])


class TestConcentration:
    """Tests for revenue concentration."""

    def test_even_distribution_has_low_concentration(self) -> None:
        """Ten identical customers give a Gini of zero.

        Returns:
            None.
        """
        result = concentration([100.0] * 10)

        assert result.gini == pytest.approx(0.0, abs=1e-9)
        assert result.largest_customer_share == pytest.approx(0.1)

    def test_concentrated_distribution_is_flagged(self) -> None:
        """One dominant customer should show a high largest share.

        Returns:
            None.
        """
        result = concentration([900.0, *([10.0] * 10)])

        assert result.largest_customer_share is not None
        assert result.largest_customer_share > 0.8
        assert result.gini is not None
        assert result.gini > 0.5

    def test_shares_are_monotonic(self) -> None:
        """A wider slice cannot hold less revenue than a narrower one.

        Returns:
            None.
        """
        result = concentration([float(value) for value in range(1, 101)])

        assert result.top_decile_share is not None
        assert result.top_quintile_share is not None
        assert result.top_half_share is not None
        assert (
            result.top_decile_share
            <= result.top_quintile_share
            <= result.top_half_share
            <= 1.0
        )

    def test_zero_and_negative_revenue_customers_are_excluded(self) -> None:
        """A customer who produced nothing does not dilute concentration.

        Returns:
            None.
        """
        result = concentration([100.0, 0.0, -5.0, 100.0])

        assert result.customers == 2
        assert result.revenue == pytest.approx(200.0)

    def test_empty_input_returns_empty_result(self) -> None:
        """No customers should return cleanly rather than raise.

        Returns:
            None.
        """
        result = concentration([])

        assert result.customers == 0
        assert result.gini is None


class TestAnalyse:
    """Tests for the combined entry point."""

    def test_analysis_covers_periods_and_concentration(self) -> None:
        """The run should return both halves of the framework.

        Returns:
            None.
        """
        result = analyse(_activity())

        assert len(result.periods) == 3
        assert result.concentration.customers == 3

    def test_summary_reports_losses_as_negative(self) -> None:
        """Churn and contraction are plotted downward, so they are negated.

        Returns:
            None.
        """
        summary = summarise(analyse(_activity()))

        second = summary["periods"][1]
        assert second["churned"] < 0
        assert second["new"] > 0
