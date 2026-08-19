"""Growth accounting and product-market fit metrics.

Decomposes revenue change into the six flows that produce it, and derives the
ratios that describe whether a merchant's growth is healthy. Unlike the
profitability scenarios, everything here is **measured**: it needs only the
transaction record, no assumed margin and no assumed acquisition spend.

The decomposition follows the quantitative product-market-fit framework
popularised by Tribe Capital, adapted to retail. Per period, each customer's
revenue falls into exactly one flow:

* **new**, first revenue this customer has ever produced
* **resurrected**, active again after at least one dormant period
* **retained**, the part of last period's revenue that repeated
* **expansion**, the increase on top of retained revenue
* **contraction**, the decrease against last period, still active
* **churned**, last period's revenue from a customer now dormant

These satisfy an identity that the tests assert directly:

    revenue(t) = retained + expansion + new + resurrected
    revenue(t-1) = retained + contraction + churned

The framework is deliberately business-model agnostic. A subscription store, a
one-off gift retailer and a wholesaler all produce these same six flows, which
is why it generalises across merchants where a fixed benchmark would not.

The framework's authors provide no absolute thresholds, and neither does this
module. A quick ratio of 1.0 separates growth from decline arithmetically, but
what counts as *healthy* depends on the business model, so the numbers are
reported and their interpretation is left to the reader.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from dataclasses import field
from typing import TYPE_CHECKING
from typing import Any

from app.core.logging import get_logger

if TYPE_CHECKING:
    from collections.abc import Sequence

logger = get_logger("analysis.growth_accounting")

# A quick ratio of exactly 1.0 means gains and losses cancel: above it total
# revenue grows, below it shrinks. This is arithmetic, not a benchmark.
BREAK_EVEN_QUICK_RATIO = 1.0


class GrowthAccountingError(Exception):
    """Base class for growth accounting failures."""


class InvalidActivityError(GrowthAccountingError):
    """Raised when the activity rows cannot be decomposed."""


@dataclass
class PeriodFlows:
    """Revenue decomposition for one period.

    Attributes:
        period: The period label
        revenue: Total revenue in this period
        previous_revenue: Total revenue in the preceding period
        new: Revenue from customers buying for the first time
        resurrected: Revenue from customers returning after dormancy
        retained: Revenue that repeated from the previous period
        expansion: Increase from customers who spent more than last period
        contraction: Decrease from customers who spent less than last period
        churned: Previous revenue from customers who went dormant
        gross_retention_rate: Retained divided by previous revenue
        quick_ratio: Revenue gained divided by revenue lost
        net_churn_rate: Net loss as a fraction of previous revenue
    """

    period: Any
    revenue: float = 0.0
    previous_revenue: float = 0.0
    new: float = 0.0
    resurrected: float = 0.0
    retained: float = 0.0
    expansion: float = 0.0
    contraction: float = 0.0
    churned: float = 0.0
    gross_retention_rate: float | None = None
    quick_ratio: float | None = None
    net_churn_rate: float | None = None


@dataclass
class ConcentrationResult:
    """How concentrated revenue is across customers.

    Attributes:
        customers: Number of customers considered
        revenue: Total revenue across them
        top_decile_share: Revenue share of the top ten per cent
        top_quintile_share: Revenue share of the top twenty per cent
        top_half_share: Revenue share of the top fifty per cent
        largest_customer_share: Revenue share of the single largest customer
        gini: Gini coefficient, 0 being perfectly even and 1 maximally
            concentrated
    """

    customers: int = 0
    revenue: float = 0.0
    top_decile_share: float | None = None
    top_quintile_share: float | None = None
    top_half_share: float | None = None
    largest_customer_share: float | None = None
    gini: float | None = None


@dataclass
class GrowthAccountingResult:
    """A complete growth accounting pass.

    Attributes:
        periods: The per-period decomposition, oldest first
        concentration: Revenue concentration across customers
    """

    periods: list[PeriodFlows] = field(default_factory=list)
    concentration: ConcentrationResult = field(default_factory=ConcentrationResult)


def decompose(activity: Sequence[dict[str, Any]]) -> list[PeriodFlows]:
    """Decompose revenue change into its six flows, period by period.

    Args:
        activity: Rows carrying "customer", "period" and "revenue". A customer
            absent from a period is treated as having produced nothing in it.

    Returns:
        One decomposition per period, oldest first.

    Raises:
        InvalidActivityError: If a row is missing a required field or carries
            a non-numeric revenue.
    """
    by_period: dict[Any, dict[Any, float]] = defaultdict(dict)

    for row in activity:
        for required in ("customer", "period", "revenue"):
            if required not in row:
                message = f"Activity row is missing {required!r}: {row!r}"
                raise InvalidActivityError(message)
        try:
            revenue = float(row["revenue"])
        except (TypeError, ValueError) as error:
            message = f"Revenue is not numeric on row {row!r}"
            raise InvalidActivityError(message) from error

        customer = row["customer"]
        period = row["period"]
        by_period[period][customer] = by_period[period].get(customer, 0.0) + revenue

    ordered = sorted(by_period)
    seen_before: set[Any] = set()
    flows: list[PeriodFlows] = []
    previous: dict[Any, float] = {}

    for index, period in enumerate(ordered):
        current = by_period[period]
        result = PeriodFlows(
            period=period,
            revenue=sum(current.values()),
            previous_revenue=sum(previous.values()),
        )

        for customer, revenue in current.items():
            before = previous.get(customer, 0.0)
            if before > 0:
                # Active in both periods: the overlap is retained, and the
                # difference is expansion or contraction.
                result.retained += min(before, revenue)
                if revenue > before:
                    result.expansion += revenue - before
                else:
                    result.contraction += before - revenue
            elif customer in seen_before:
                result.resurrected += revenue
            else:
                result.new += revenue

        for customer, before in previous.items():
            if current.get(customer, 0.0) == 0 and before > 0:
                result.churned += before

        if result.previous_revenue > 0:
            result.gross_retention_rate = result.retained / result.previous_revenue
            result.net_churn_rate = (
                result.churned
                + result.contraction
                - result.resurrected
                - result.expansion
            ) / result.previous_revenue

        lost = result.churned + result.contraction
        gained = result.new + result.resurrected + result.expansion
        if lost > 0:
            result.quick_ratio = gained / lost
        elif index > 0 and gained > 0:
            # Nothing was lost at all. The ratio is unbounded rather than
            # undefined, but reporting infinity is unhelpful, so it stays None
            # and the flows themselves carry the story.
            result.quick_ratio = None

        seen_before.update(current)
        previous = current
        flows.append(result)

    return flows


def concentration(
    revenue_per_customer: Sequence[float],
) -> ConcentrationResult:
    """Measure how concentrated revenue is across customers.

    Concentration is the part of the framework that distinguishes a scalable
    merchant from one that merely has a few large accounts. A store whose top
    two customers produce most of its revenue behaves like a wholesaler with
    key accounts, whatever its retail branding says.

    Args:
        revenue_per_customer: Revenue attributable to each customer.

    Returns:
        The concentration shares and Gini coefficient.
    """
    values = sorted(
        (float(value) for value in revenue_per_customer if float(value) > 0),
        reverse=True,
    )
    result = ConcentrationResult(customers=len(values), revenue=sum(values))

    if not values or result.revenue <= 0:
        return result

    def share(fraction: float) -> float:
        count = max(1, round(len(values) * fraction))
        return sum(values[:count]) / result.revenue

    result.top_decile_share = share(0.10)
    result.top_quintile_share = share(0.20)
    result.top_half_share = share(0.50)
    result.largest_customer_share = values[0] / result.revenue

    # Gini over the ascending distribution, the standard formulation.
    ascending = sorted(values)
    total = sum(ascending)
    count = len(ascending)
    weighted = sum((index + 1) * value for index, value in enumerate(ascending))
    result.gini = (2 * weighted) / (count * total) - (count + 1) / count

    return result


def analyse(activity: Sequence[dict[str, Any]]) -> GrowthAccountingResult:
    """Run the full decomposition and concentration analysis.

    Args:
        activity: Rows carrying "customer", "period" and "revenue".

    Returns:
        The per-period flows and the revenue concentration.

    Raises:
        InvalidActivityError: If the activity rows are unusable.
    """
    flows = decompose(activity)

    totals: dict[Any, float] = defaultdict(float)
    for row in activity:
        totals[row["customer"]] += float(row["revenue"])

    result = GrowthAccountingResult(
        periods=flows, concentration=concentration(list(totals.values()))
    )

    logger.info(
        "growth_accounting_complete",
        periods=len(flows),
        customers=result.concentration.customers,
    )
    return result


def summarise(result: GrowthAccountingResult) -> dict[str, Any]:
    """Summarise a run for logging or a notebook.

    Args:
        result: The analysis to summarise.

    Returns:
        The per-period ratios and the concentration shares.
    """
    return {
        "periods": [
            {
                "period": str(flows.period),
                "revenue": round(flows.revenue, 2),
                "new": round(flows.new, 2),
                "resurrected": round(flows.resurrected, 2),
                "expansion": round(flows.expansion, 2),
                "contraction": round(-flows.contraction, 2),
                "churned": round(-flows.churned, 2),
                "quick_ratio": (
                    round(flows.quick_ratio, 3)
                    if flows.quick_ratio is not None
                    else None
                ),
                "net_churn_rate": (
                    round(flows.net_churn_rate, 4)
                    if flows.net_churn_rate is not None
                    else None
                ),
                "gross_retention_rate": (
                    round(flows.gross_retention_rate, 4)
                    if flows.gross_retention_rate is not None
                    else None
                ),
            }
            for flows in result.periods
        ],
        "concentration": {
            "customers": result.concentration.customers,
            "top_decile_share": result.concentration.top_decile_share,
            "top_quintile_share": result.concentration.top_quintile_share,
            "largest_customer_share": result.concentration.largest_customer_share,
            "gini": result.concentration.gini,
        },
    }
