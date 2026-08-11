"""Growth accounting, concentration, and profitability scenarios.

Backs the economics of chapter 7. The first half is measured; the second half
is explicitly not, and the notebook keeps the two visibly apart.

    uv run python notebooks/06_growth_and_profitability.py
"""

# %%
from __future__ import annotations

import asyncio
from pathlib import Path

import matplotlib
import matplotlib.pyplot as plt
import pandas as pd

from app.database import async_session_factory
from app.services.growth_accounting_service import GrowthAccountingService
from app.services.profitability_service import ProfitabilityService

matplotlib.use("Agg")

FIGURES = Path(__file__).resolve().parent.parent / "thesis" / "figures"
FIGURES.mkdir(parents=True, exist_ok=True)


# %%
async def load() -> tuple[object, list[dict]]:
    """Run growth accounting and the profitability sweep.

    Returns:
        The growth accounting result and the sensitivity grid.
    """
    async with async_session_factory() as session:
        growth = await GrowthAccountingService(session).run("month")
        # The ranges are chosen to straddle the 3:1 decision boundary for
        # this merchant, whose observed revenue per customer is around 2900.
        # A narrower range would pass everywhere and demonstrate nothing.
        sweep = await ProfitabilityService(session).sensitivity(
            gross_margins=[0.15, 0.30, 0.45, 0.60],
            acquisition_costs=[100.0, 250.0, 500.0, 900.0],
        )
        return growth, sweep


growth, sweep = asyncio.run(load())

# %% [markdown]
# ## Revenue decomposition (measured)
#
# Losses are plotted downward. The identity that these six flows must satisfy
# is asserted in the test suite, so the chart cannot silently drift from the
# arithmetic.

# %%
flows = pd.DataFrame([
    {
        "period": row.period,
        "new": row.new,
        "resurrected": row.resurrected,
        "expansion": row.expansion,
        "contraction": -row.contraction,
        "churned": -row.churned,
        "quick_ratio": row.quick_ratio,
        "net_churn_rate": row.net_churn_rate,
    }
    for row in growth.periods
]).set_index("period")

print(flows.round(2).to_string())

columns = ["new", "resurrected", "expansion", "contraction", "churned"]
# Greek names for the plot, matching the terminology used in the manuscript.
FLOW_LABELS = {
    "new": "νέα",
    "resurrected": "αναβιωμένα",
    "expansion": "επέκταση",
    "contraction": "συρρίκνωση",
    "churned": "απώλεια",
}
figure, axes = plt.subplots(figsize=(12, 5))
bottom_positive = pd.Series(0.0, index=flows.index)
bottom_negative = pd.Series(0.0, index=flows.index)
for column in columns:
    values = flows[column]
    bottom = bottom_positive if values.ge(0).all() else bottom_negative
    axes.bar(flows.index, values, bottom=bottom, width=20,
             label=FLOW_LABELS[column])
    if values.ge(0).all():
        bottom_positive = bottom_positive + values
    else:
        bottom_negative = bottom_negative + values
axes.axhline(0, color="black", linewidth=0.8)
axes.set_ylabel("Έσοδα")
axes.set_title("Αποσύνθεση της μεταβολής των εσόδων")
axes.legend(ncol=5)
figure.autofmt_xdate()
figure.tight_layout()
figure.savefig(FIGURES / "growth_accounting.pdf")

# %%
ratios = flows[["quick_ratio"]].dropna()
if not ratios.empty:
    figure, axes = plt.subplots(figsize=(11, 3.5))
    axes.plot(ratios.index, ratios["quick_ratio"], marker="o")
    axes.axhline(1.0, color="red", linestyle="--",
                 label="ισοσκέλιση κερδών και απωλειών")
    axes.set_ylabel("Ταχύς λόγος")
    axes.set_title("Ταχύς λόγος ανά μήνα")
    axes.legend()
    figure.autofmt_xdate()
    figure.tight_layout()
    figure.savefig(FIGURES / "quick_ratio.pdf")

# %% [markdown]
# ## Revenue concentration (measured)

# %%
concentration = growth.concentration
print(f"customers               {concentration.customers:,}")
print(f"top decile share        {concentration.top_decile_share:.3f}")
print(f"top quintile share      {concentration.top_quintile_share:.3f}")
print(f"top half share          {concentration.top_half_share:.3f}")
print(f"largest customer share  {concentration.largest_customer_share:.4f}")
print(f"gini                    {concentration.gini:.3f}")

# %% [markdown]
# ## Profitability sensitivity (NOT measured)
#
# Everything below rests on assumed margins and acquisition costs. The data
# contains neither. The point of the grid is precisely that the conclusion
# moves with the assumption.

# %%
grid = pd.DataFrame([
    {
        "gross_margin": row["assumptions"]["gross_margin"],
        "acquisition_cost": row["assumptions"]["customer_acquisition_cost"],
        "lifetime_value": round(row["lifetime_value"], 2),
        "ltv_cac": (round(row["lifetime_value_to_acquisition_cost"], 2)
                    if row["lifetime_value_to_acquisition_cost"] else None),
        "meets_3to1": row["meets_ratio_benchmark"],
    }
    for row in sweep
])
print(grid.to_string(index=False))

verdicts = set(grid["meets_3to1"].dropna())
print("\nDistinct verdicts across the grid:", verdicts)
if verdicts == {True, False}:
    print("The same observed data both passes and fails the 3:1 benchmark,")
    print("purely according to the assumed margin and acquisition cost.")
    print("That dependence is the finding, not any single cell.")

pivot = grid.pivot(index="gross_margin", columns="acquisition_cost", values="ltv_cac")
figure, axes = plt.subplots(figsize=(7, 4))
image = axes.imshow(pivot.to_numpy(dtype=float), aspect="auto", cmap="RdYlGn")
axes.set_xticks(range(len(pivot.columns)))
axes.set_xticklabels(pivot.columns)
axes.set_yticks(range(len(pivot.index)))
axes.set_yticklabels(pivot.index)
axes.set_xlabel("Υποτιθέμενο κόστος απόκτησης")
axes.set_ylabel("Υποτιθέμενο περιθώριο")
axes.set_title("Λόγος LTV:CAC υπό διαφορετικές παραδοχές")
for row_index, margin in enumerate(pivot.index):
    for column_index, cost in enumerate(pivot.columns):
        ratio = pivot.loc[margin, cost]
        axes.text(column_index, row_index, f"{ratio:.2f}", ha="center",
                  va="center", fontsize=9)
figure.colorbar(image, ax=axes, label="LTV:CAC")
figure.tight_layout()
figure.savefig(FIGURES / "profitability_sensitivity.pdf")

print("\n" + sweep[0]["disclaimer"])
