"""Profitability scenarios over assumed costs.

**This module computes scenarios, never measurements.**

The transaction data behind this project records what was sold and for how
much. It records no cost of goods and no marketing spend. Profitability
therefore cannot be measured from it, and any figure claiming otherwise would
be an invention dressed as a finding.

What can be done honestly is a sensitivity analysis: state a gross margin and
an acquisition cost explicitly, vary them, and report what follows *if* they
hold. Every result this module returns carries the assumptions that produced
it, precisely so the two can never be separated downstream.

Published reference points, used to bound plausible inputs rather than to
assert this business's numbers:

* Gross margin by category spans roughly 15-30 per cent for electronics up to
  65-85 per cent for beauty and supplements.
* An LTV:CAC ratio of about 3:1 is widely treated as healthy.
* A CAC payback period of 6 to 12 months is typical for direct-to-consumer
  retail.

These are practitioner benchmarks, not peer-reviewed findings, and the thesis
cites them as footnoted industry estimates rather than in its bibliography.
"""

from __future__ import annotations

from dataclasses import dataclass
from dataclasses import field
from typing import TYPE_CHECKING
from typing import Any

from app.core.logging import get_logger

if TYPE_CHECKING:
    from collections.abc import Sequence

logger = get_logger("analysis.profitability")

# Sentence attached to every result. It exists so that a scenario cannot be
# quoted as a measurement by accident, whether in an API response, a notebook
# or the manuscript.
SCENARIO_DISCLAIMER = (
    "Scenario output, not a measurement. The source data contains no cost of "
    "goods and no marketing spend, so these figures follow from the stated "
    "assumptions and hold only insofar as those assumptions do."
)

# Practitioner reference points, reported alongside results for comparison.
HEALTHY_LIFETIME_VALUE_TO_ACQUISITION_COST = 3.0
HEALTHY_PAYBACK_MONTHS = 12.0


class ProfitabilityError(Exception):
    """Base class for scenario failures."""


class InvalidAssumptionsError(ProfitabilityError):
    """Raised when the stated assumptions cannot produce a scenario."""


@dataclass(frozen=True, slots=True)
class Assumptions:
    """The inputs a scenario rests on.

    Attributes:
        gross_margin: Fraction of revenue left after cost of goods, in (0, 1]
        customer_acquisition_cost: Marketing spend per newly acquired customer
        operating_cost_per_period: Fixed costs per period, when modelled
    """

    gross_margin: float
    customer_acquisition_cost: float
    operating_cost_per_period: float = 0.0

    def validate(self) -> None:
        """Reject assumptions that cannot produce a meaningful scenario.

        Raises:
            InvalidAssumptionsError: If any assumption is out of range.
        """
        if not 0 < self.gross_margin <= 1:
            message = "Gross margin must fall in (0, 1]"
            raise InvalidAssumptionsError(message)
        if self.customer_acquisition_cost < 0:
            message = "Customer acquisition cost cannot be negative"
            raise InvalidAssumptionsError(message)
        if self.operating_cost_per_period < 0:
            message = "Operating cost cannot be negative"
            raise InvalidAssumptionsError(message)


@dataclass
class PeriodProjection:
    """One projected period under a scenario.

    Attributes:
        index: Position in the projection, starting at 0
        revenue: Revenue for the period, observed or forecast
        gross_profit: Revenue multiplied by the assumed margin
        acquisition_spend: Assumed cost of the period's new customers
        operating_cost: Assumed fixed cost for the period
        net_profit: Gross profit less acquisition and operating costs
        cumulative_net_profit: Running total of net profit
    """

    index: int
    revenue: float
    gross_profit: float
    acquisition_spend: float
    operating_cost: float
    net_profit: float
    cumulative_net_profit: float


@dataclass
class ScenarioResult:
    """A complete profitability scenario.

    Attributes:
        assumptions: The inputs this scenario rests on
        projections: Period-by-period projection
        lifetime_value: Assumed gross profit per customer over their life
        lifetime_value_to_acquisition_cost: LTV divided by CAC, or None when
            no acquisition cost was assumed
        payback_periods: Periods until a customer's gross profit repays their
            acquisition cost, or None when it never does
        break_even_index: First period where cumulative net profit turns
            positive, or None if it does not within the projection
        disclaimer: The scenario warning, carried with every result
    """

    assumptions: Assumptions
    projections: list[PeriodProjection] = field(default_factory=list)
    lifetime_value: float | None = None
    lifetime_value_to_acquisition_cost: float | None = None
    payback_periods: float | None = None
    break_even_index: int | None = None
    disclaimer: str = SCENARIO_DISCLAIMER


def project(
    revenues: Sequence[float],
    assumptions: Assumptions,
    new_customers_per_period: Sequence[int] | None = None,
) -> ScenarioResult:
    """Project profit across periods under the stated assumptions.

    Args:
        revenues: Revenue per period, observed or forecast, oldest first.
        assumptions: The margin and cost inputs to apply.
        new_customers_per_period: Newly acquired customers per period, used to
            derive acquisition spend. Zero spend is assumed when omitted.

    Returns:
        The projection with its derived ratios.

    Raises:
        InvalidAssumptionsError: If the assumptions or inputs are unusable.
    """
    assumptions.validate()

    if new_customers_per_period is not None and len(new_customers_per_period) != len(
        revenues
    ):
        message = "New customer counts must align with the revenue periods"
        raise InvalidAssumptionsError(message)

    result = ScenarioResult(assumptions=assumptions)
    cumulative = 0.0

    for index, revenue in enumerate(revenues):
        acquired = (
            new_customers_per_period[index]
            if new_customers_per_period is not None
            else 0
        )
        gross_profit = float(revenue) * assumptions.gross_margin
        acquisition_spend = acquired * assumptions.customer_acquisition_cost
        net_profit = (
            gross_profit - acquisition_spend - assumptions.operating_cost_per_period
        )
        cumulative += net_profit

        result.projections.append(
            PeriodProjection(
                index=index,
                revenue=float(revenue),
                gross_profit=gross_profit,
                acquisition_spend=acquisition_spend,
                operating_cost=assumptions.operating_cost_per_period,
                net_profit=net_profit,
                cumulative_net_profit=cumulative,
            )
        )

        if result.break_even_index is None and cumulative > 0:
            result.break_even_index = index

    logger.info(
        "scenario_projected",
        periods=len(revenues),
        gross_margin=assumptions.gross_margin,
        break_even_index=result.break_even_index,
    )
    return result


def unit_economics(
    average_customer_revenue: float,
    assumptions: Assumptions,
    average_periods_per_customer: float | None = None,
) -> dict[str, Any]:
    """Derive per-customer economics under the stated assumptions.

    Lifetime value here is gross profit, not revenue. Comparing revenue
    against acquisition cost would overstate the ratio by exactly the cost of
    goods, which is the most common way this figure is inflated.

    Args:
        average_customer_revenue: Observed revenue per customer to date.
        assumptions: The margin and cost inputs to apply.
        average_periods_per_customer: Average number of periods a customer
            remains active, used to derive a payback period.

    Returns:
        Lifetime value, the LTV:CAC ratio, the payback period and the
        benchmarks they should be read against, with the disclaimer.

    Raises:
        InvalidAssumptionsError: If the assumptions or inputs are unusable.
    """
    assumptions.validate()
    if average_customer_revenue < 0:
        message = "Average customer revenue cannot be negative"
        raise InvalidAssumptionsError(message)

    lifetime_value = average_customer_revenue * assumptions.gross_margin

    ratio: float | None = None
    if assumptions.customer_acquisition_cost > 0:
        ratio = lifetime_value / assumptions.customer_acquisition_cost

    # Payback needs a rate of profit, so it needs to know over how many
    # periods the customer's value accrued.
    payback: float | None = None
    if (
        assumptions.customer_acquisition_cost > 0
        and average_periods_per_customer
        and average_periods_per_customer > 0
        and lifetime_value > 0
    ):
        profit_per_period = lifetime_value / average_periods_per_customer
        payback = assumptions.customer_acquisition_cost / profit_per_period

    return {
        "lifetime_value": lifetime_value,
        "lifetime_value_to_acquisition_cost": ratio,
        "payback_periods": payback,
        "healthy_lifetime_value_to_acquisition_cost": (
            HEALTHY_LIFETIME_VALUE_TO_ACQUISITION_COST
        ),
        "healthy_payback_periods": HEALTHY_PAYBACK_MONTHS,
        "meets_ratio_benchmark": (
            ratio >= HEALTHY_LIFETIME_VALUE_TO_ACQUISITION_COST
            if ratio is not None
            else None
        ),
        "assumptions": {
            "gross_margin": assumptions.gross_margin,
            "customer_acquisition_cost": assumptions.customer_acquisition_cost,
        },
        "disclaimer": SCENARIO_DISCLAIMER,
    }


def sweep(
    average_customer_revenue: float,
    gross_margins: Sequence[float],
    acquisition_costs: Sequence[float],
    average_periods_per_customer: float | None = None,
) -> list[dict[str, Any]]:
    """Evaluate unit economics across a grid of assumptions.

    A single scenario invites being read as a prediction. A sweep makes the
    dependence on the inputs visible, which is the entire point of presenting
    this as sensitivity analysis.

    Args:
        average_customer_revenue: Observed revenue per customer to date.
        gross_margins: Margin values to evaluate.
        acquisition_costs: Acquisition cost values to evaluate.
        average_periods_per_customer: Average active periods per customer.

    Returns:
        One row per combination of assumptions.

    Raises:
        InvalidAssumptionsError: If any combination is unusable.
    """
    if not gross_margins or not acquisition_costs:
        message = "A sweep needs at least one margin and one acquisition cost"
        raise InvalidAssumptionsError(message)

    rows: list[dict[str, Any]] = []
    for margin in gross_margins:
        for cost in acquisition_costs:
            rows.append(
                unit_economics(
                    average_customer_revenue,
                    Assumptions(gross_margin=margin, customer_acquisition_cost=cost),
                    average_periods_per_customer,
                )
            )
    return rows
