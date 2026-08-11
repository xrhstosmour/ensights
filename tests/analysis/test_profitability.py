"""Unit tests for profitability scenarios.

Beyond the arithmetic, these tests pin the module's central property: nothing
it returns may be mistaken for a measurement.
"""

from __future__ import annotations

import pytest

from app.analysis.profitability import SCENARIO_DISCLAIMER
from app.analysis.profitability import Assumptions
from app.analysis.profitability import InvalidAssumptionsError
from app.analysis.profitability import project
from app.analysis.profitability import sweep
from app.analysis.profitability import unit_economics


class TestAssumptions:
    """Tests for assumption validation."""

    @pytest.mark.parametrize("margin", [0.0, -0.1, 1.1])
    def test_out_of_range_margin_is_rejected(self, margin: float) -> None:
        """A margin outside (0, 1] cannot describe a real business.

        Args:
            margin: Margin under test.

        Returns:
            None.
        """
        with pytest.raises(InvalidAssumptionsError, match="Gross margin"):
            Assumptions(gross_margin=margin, customer_acquisition_cost=10.0).validate()

    def test_negative_acquisition_cost_is_rejected(self) -> None:
        """Acquiring a customer cannot cost less than nothing.

        Returns:
            None.
        """
        with pytest.raises(InvalidAssumptionsError):
            Assumptions(gross_margin=0.5, customer_acquisition_cost=-1.0).validate()

    def test_full_margin_is_allowed(self) -> None:
        """A margin of exactly one is legitimate for a zero-cost good.

        Returns:
            None.
        """
        Assumptions(gross_margin=1.0, customer_acquisition_cost=0.0).validate()


class TestProject:
    """Tests for the period projection."""

    def test_gross_profit_applies_the_margin(self) -> None:
        """Gross profit is revenue scaled by the assumed margin.

        Returns:
            None.
        """
        result = project(
            [1000.0, 2000.0],
            Assumptions(gross_margin=0.4, customer_acquisition_cost=0.0),
        )

        assert result.projections[0].gross_profit == pytest.approx(400.0)
        assert result.projections[1].gross_profit == pytest.approx(800.0)

    def test_acquisition_spend_scales_with_new_customers(self) -> None:
        """Spend is the per-customer cost times the customers acquired.

        Returns:
            None.
        """
        result = project(
            [1000.0, 1000.0],
            Assumptions(gross_margin=0.5, customer_acquisition_cost=20.0),
            new_customers_per_period=[10, 5],
        )

        assert result.projections[0].acquisition_spend == pytest.approx(200.0)
        assert result.projections[1].acquisition_spend == pytest.approx(100.0)

    def test_net_profit_subtracts_both_cost_lines(self) -> None:
        """Net is gross less acquisition and operating cost.

        Returns:
            None.
        """
        result = project(
            [1000.0],
            Assumptions(
                gross_margin=0.5,
                customer_acquisition_cost=20.0,
                operating_cost_per_period=100.0,
            ),
            new_customers_per_period=[10],
        )

        # 500 gross, less 200 acquisition, less 100 operating.
        assert result.projections[0].net_profit == pytest.approx(200.0)

    def test_cumulative_profit_accumulates(self) -> None:
        """The running total should add each period's net profit.

        Returns:
            None.
        """
        result = project(
            [1000.0, 1000.0, 1000.0],
            Assumptions(gross_margin=0.5, customer_acquisition_cost=0.0),
        )

        totals = [row.cumulative_net_profit for row in result.projections]
        assert totals == pytest.approx([500.0, 1000.0, 1500.0])

    def test_break_even_is_the_first_positive_period(self) -> None:
        """Break-even is where the cumulative total first turns positive.

        Returns:
            None.
        """
        # Heavy acquisition spend up front, then none.
        result = project(
            [1000.0, 1000.0, 1000.0],
            Assumptions(gross_margin=0.5, customer_acquisition_cost=100.0),
            new_customers_per_period=[8, 0, 0],
        )

        # Period 0: 500 gross less 800 spend equals -300 cumulative.
        # Period 1: +500 gives +200, so break-even is period 1.
        assert result.break_even_index == 1

    def test_break_even_is_none_when_never_reached(self) -> None:
        """A scenario that never turns a profit must say so.

        Returns:
            None.
        """
        result = project(
            [100.0, 100.0],
            Assumptions(
                gross_margin=0.1,
                customer_acquisition_cost=0.0,
                operating_cost_per_period=1000.0,
            ),
        )

        assert result.break_even_index is None

    def test_misaligned_customer_counts_are_rejected(self) -> None:
        """Mismatched series would silently attribute spend to wrong periods.

        Returns:
            None.
        """
        with pytest.raises(InvalidAssumptionsError, match="align"):
            project(
                [1000.0, 2000.0],
                Assumptions(gross_margin=0.5, customer_acquisition_cost=10.0),
                new_customers_per_period=[1],
            )

    def test_result_carries_the_disclaimer(self) -> None:
        """A projection must never travel without its warning.

        Returns:
            None.
        """
        result = project(
            [100.0], Assumptions(gross_margin=0.5, customer_acquisition_cost=0.0)
        )

        assert result.disclaimer == SCENARIO_DISCLAIMER
        assert "not a measurement" in result.disclaimer

    def test_result_carries_its_assumptions(self) -> None:
        """The inputs must stay attached to the outputs.

        Returns:
            None.
        """
        assumptions = Assumptions(gross_margin=0.35, customer_acquisition_cost=12.0)

        result = project([100.0], assumptions)

        assert result.assumptions is assumptions


class TestUnitEconomics:
    """Tests for the per-customer ratios."""

    def test_lifetime_value_is_gross_profit_not_revenue(self) -> None:
        """Using revenue would overstate the ratio by the cost of goods.

        Returns:
            None.
        """
        economics = unit_economics(
            1000.0, Assumptions(gross_margin=0.4, customer_acquisition_cost=100.0)
        )

        assert economics["lifetime_value"] == pytest.approx(400.0)
        # Had revenue been used, the ratio would read 10.0 rather than 4.0.
        assert economics["lifetime_value_to_acquisition_cost"] == pytest.approx(4.0)

    def test_ratio_is_compared_against_the_benchmark(self) -> None:
        """The result should say whether it clears the 3:1 reference point.

        Returns:
            None.
        """
        healthy = unit_economics(
            1000.0, Assumptions(gross_margin=0.5, customer_acquisition_cost=100.0)
        )
        unhealthy = unit_economics(
            1000.0, Assumptions(gross_margin=0.1, customer_acquisition_cost=100.0)
        )

        assert healthy["meets_ratio_benchmark"] is True
        assert unhealthy["meets_ratio_benchmark"] is False

    def test_ratio_is_none_without_an_acquisition_cost(self) -> None:
        """Dividing by zero spend is undefined, not infinite.

        Returns:
            None.
        """
        economics = unit_economics(
            1000.0, Assumptions(gross_margin=0.5, customer_acquisition_cost=0.0)
        )

        assert economics["lifetime_value_to_acquisition_cost"] is None
        assert economics["meets_ratio_benchmark"] is None

    def test_payback_period_is_exact(self) -> None:
        """Payback is acquisition cost divided by profit per period.

        Returns:
            None.
        """
        economics = unit_economics(
            1200.0,
            Assumptions(gross_margin=0.5, customer_acquisition_cost=100.0),
            average_periods_per_customer=12.0,
        )

        # 600 lifetime gross profit over 12 periods is 50 per period, so 100
        # of acquisition cost is repaid in 2 periods.
        assert economics["payback_periods"] == pytest.approx(2.0)

    def test_payback_is_none_without_a_lifespan(self) -> None:
        """Without a lifespan there is no rate, so no payback period.

        Returns:
            None.
        """
        economics = unit_economics(
            1000.0, Assumptions(gross_margin=0.5, customer_acquisition_cost=100.0)
        )

        assert economics["payback_periods"] is None

    def test_negative_revenue_is_rejected(self) -> None:
        """A negative average revenue is a caller error.

        Returns:
            None.
        """
        with pytest.raises(InvalidAssumptionsError):
            unit_economics(
                -1.0, Assumptions(gross_margin=0.5, customer_acquisition_cost=10.0)
            )

    def test_economics_carry_the_disclaimer_and_assumptions(self) -> None:
        """Every result must be self-describing.

        Returns:
            None.
        """
        economics = unit_economics(
            1000.0, Assumptions(gross_margin=0.5, customer_acquisition_cost=100.0)
        )

        assert economics["disclaimer"] == SCENARIO_DISCLAIMER
        assert economics["assumptions"]["gross_margin"] == 0.5
        assert economics["assumptions"]["customer_acquisition_cost"] == 100.0


class TestSweep:
    """Tests for the sensitivity grid."""

    def test_sweep_covers_every_combination(self) -> None:
        """The grid is the cross product of the stated ranges.

        Returns:
            None.
        """
        rows = sweep(1000.0, [0.2, 0.5, 0.8], [50.0, 100.0])

        assert len(rows) == 6

    def test_sweep_shows_the_answer_depends_on_the_inputs(self) -> None:
        """The same data can clear or fail the benchmark by assumption alone.

        Returns:
            None.
        """
        rows = sweep(1000.0, [0.1, 0.9], [100.0])

        verdicts = {row["meets_ratio_benchmark"] for row in rows}

        # This is the point of the sweep: identical observed revenue yields
        # opposite conclusions purely from the assumed margin.
        assert verdicts == {True, False}

    def test_every_sweep_row_carries_the_disclaimer(self) -> None:
        """No row may be lifted out of the grid without its warning.

        Returns:
            None.
        """
        rows = sweep(1000.0, [0.3, 0.6], [20.0, 80.0])

        assert all(row["disclaimer"] == SCENARIO_DISCLAIMER for row in rows)

    def test_empty_ranges_are_rejected(self) -> None:
        """A sweep with nothing to vary is a caller error.

        Returns:
            None.
        """
        with pytest.raises(InvalidAssumptionsError):
            sweep(1000.0, [], [10.0])
