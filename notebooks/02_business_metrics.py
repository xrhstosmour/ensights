"""Business and unit-economics metrics measured from the transactions.

Backs the measured half of chapter 7: GMV, repeat purchase rate, cohort
retention and RFM. The scenario half, profitability, is deliberately a separate
notebook, because it rests on assumptions rather than measurements and the two
should never be read as the same kind of number.

    uv sync --extra analysis
    uv run python notebooks/02_business_metrics.py
"""

# %%
from __future__ import annotations

import asyncio
from pathlib import Path

import matplotlib
import matplotlib.pyplot as plt
import pandas as pd

from app.database import async_session_factory
from app.services.business_metrics_service import BusinessMetricsService

matplotlib.use("Agg")

FIGURES = Path(__file__).resolve().parent.parent / "thesis" / "figures"
FIGURES.mkdir(parents=True, exist_ok=True)


# %%
async def load_metrics() -> dict[str, object]:
    """Run every measured metric and collect the results.

    Returns:
        Mapping of metric name to its rows or summary.
    """
    async with async_session_factory() as session:
        service = BusinessMetricsService(session)
        return {
            "gmv": pd.DataFrame(
                await service.gross_merchandise_value(granularity="month")
            ),
            "summary": await service.customer_summary(),
            "cohorts": pd.DataFrame(await service.cohort_retention()),
            "rfm": pd.DataFrame(await service.rfm()),
        }


metrics = asyncio.run(load_metrics())

# %% [markdown]
# ## Gross merchandise value
#
# GMV is reported gross of refunds, the conventional definition. The refunded
# and net columns sit beside it so neither number can quietly disappear.

# %%
gmv = metrics["gmv"]
assert isinstance(gmv, pd.DataFrame)
print(gmv.to_string(index=False))

if not gmv.empty:
    figure, axes = plt.subplots(figsize=(11, 4))
    axes.bar(
        gmv["period"],
        gmv["gross_merchandise_value"].astype(float),
        width=20,
        label="GMV",
    )
    axes.plot(
        gmv["period"],
        gmv["net_merchandise_value"].astype(float),
        color="black",
        marker="o",
        label="Καθαρή αξία",
    )
    axes.set_ylabel("Αξία")
    axes.set_title("Ακαθάριστη και καθαρή αξία πωλήσεων ανά μήνα")
    axes.legend()
    figure.autofmt_xdate()
    figure.tight_layout()
    figure.savefig(FIGURES / "gross_merchandise_value.pdf")

# %% [markdown]
# ## Repeat customers

# %%
summary = metrics["summary"]
assert isinstance(summary, dict)
for key, value in summary.items():
    print(f"{key:32} {value}")

# %% [markdown]
# ## Cohort retention
#
# Rows are acquisition months, columns are whole months since acquisition.
# The diagonal shape is expected: later cohorts have had fewer months in
# which to come back, so the lower-right of the grid is empty rather than
# zero.

# %%
cohorts = metrics["cohorts"]
assert isinstance(cohorts, pd.DataFrame)

if not cohorts.empty:
    grid = cohorts.pivot_table(
        index="cohort_month",
        columns="period_index",
        values="retention_rate",
        aggfunc="first",
    )
    print((grid * 100).round(1).to_string())

    figure, axes = plt.subplots(figsize=(10, 5))
    image = axes.imshow(grid.to_numpy(dtype=float), aspect="auto", cmap="Blues")
    axes.set_xticks(range(len(grid.columns)))
    axes.set_xticklabels(grid.columns)
    axes.set_yticks(range(len(grid.index)))
    axes.set_yticklabels([str(value)[:7] for value in grid.index])
    axes.set_xlabel("Μήνες από την απόκτηση")
    axes.set_ylabel("Κοόρτη")
    axes.set_title("Διατήρηση πελατών ανά κοόρτη")
    figure.colorbar(image, ax=axes, label="Ποσοστό διατήρησης")
    figure.tight_layout()
    figure.savefig(FIGURES / "cohort_retention.pdf")

# %% [markdown]
# ## RFM
#
# These are the features the customer-level clustering consumes in chapter 6.
# The monetary column is observed value to date; it is not a predicted
# lifetime value, and no model has been fitted here.

# %%
rfm = metrics["rfm"]
assert isinstance(rfm, pd.DataFrame)
print(rfm.head(15).to_string(index=False))

if not rfm.empty:
    print("\nΠεριγραφικά στατιστικά:")
    print(
        rfm[["recency_days", "frequency", "monetary"]]
        .astype(float)
        .describe()
        .round(2)
        .to_string()
    )

    figure, axes = plt.subplots(1, 3, figsize=(13, 4))
    for index, column in enumerate(["recency_days", "frequency", "monetary"]):
        axes[index].hist(rfm[column].astype(float), bins=30)
        axes[index].set_title(column)
    figure.suptitle("Κατανομές RFM")
    figure.tight_layout()
    figure.savefig(FIGURES / "rfm_distributions.pdf")

# %% [markdown]
# ## Note on what is missing
#
# Nothing above assumes a cost of goods or an acquisition spend, because the
# dataset contains neither. Any statement about profitability therefore
# belongs to the scenario notebook, where the assumptions are explicit and
# varied, and never to this one.
