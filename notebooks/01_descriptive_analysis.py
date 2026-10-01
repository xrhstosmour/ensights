"""Descriptive analysis of the e-commerce transactions.

Backs chapter 4 of the thesis: the seven questions the business asked.

This is a jupytext-style percent script rather than a `.ipynb`, so it reviews
as a readable diff and cannot carry stale outputs into version control. Open it
directly in Jupyter (`uv run jupyter lab`, then right-click, Open With,
Notebook) or run it as a plain script.

    uv sync --extra analysis
    uv run python notebooks/01_descriptive_analysis.py

Figures are written to `thesis/figures/`, which is where the manuscript picks
them up.
"""

# %%
from __future__ import annotations

import asyncio
from pathlib import Path

import matplotlib
import matplotlib.pyplot as plt
import pandas as pd

from app.database import async_session_factory
from app.services.analytics_service import AnalyticsService

# Non-interactive backend so the script also runs headless, for example in CI.
matplotlib.use("Agg")

FIGURES = Path(__file__).resolve().parent.parent / "thesis" / "figures"
FIGURES.mkdir(parents=True, exist_ok=True)

# %% [markdown]
# ## Loading the reports
#
# Every figure below comes from the same service the API exposes, so the
# thesis and the running system can never disagree about a number.


# %%
async def load_reports() -> dict[str, pd.DataFrame]:
    """Run every descriptive report and collect them as data frames.

    Returns:
        Mapping of report name to its rows.
    """
    async with async_session_factory() as session:
        service = AnalyticsService(session)
        return {
            "top_products": pd.DataFrame(await service.top_products(limit=15)),
            "top_customers": pd.DataFrame(await service.top_customers(limit=15)),
            "top_regions": pd.DataFrame(await service.top_regions(limit=15)),
            "sales_monthly": pd.DataFrame(
                await service.sales_over_time(granularity="month")
            ),
            "sales_weekday": pd.DataFrame(await service.sales_by_weekday()),
            "returns": pd.DataFrame(await service.top_returned_products(limit=15)),
            "price_bands": pd.DataFrame(await service.sales_by_price_band()),
            "characteristics": pd.DataFrame(await service.sales_by_characteristic()),
        }


reports = asyncio.run(load_reports())

for name, frame in reports.items():
    print(f"{name}: {len(frame)} rows")

# %% [markdown]
# ## 1. Products with the highest sales

# %%
products = reports["top_products"]
print(products.head(10).to_string(index=False))

if not products.empty:
    figure, axes = plt.subplots(figsize=(10, 5))
    top = products.head(10).iloc[::-1]
    axes.barh(top["description"].fillna(top["stock_code"]), top["revenue"].astype(float))
    axes.set_xlabel("Έσοδα")
    axes.set_title("Προϊόντα με τις μεγαλύτερες πωλήσεις")
    figure.tight_layout()
    figure.savefig(FIGURES / "top_products.pdf")

# %% [markdown]
# ## 2. Customers with the most purchases
#
# Anonymous sales are excluded here, and only here. They stay in every other
# breakdown, because a sale without a known buyer is still a sale.

# %%
customers = reports["top_customers"]
print(customers.head(10).to_string(index=False))

if not customers.empty:
    figure, axes = plt.subplots(figsize=(10, 5))
    top = customers.head(10).iloc[::-1]
    axes.barh(top["customer_identifier"].astype(str), top["revenue"].astype(float))
    axes.set_xlabel("Έσοδα")
    axes.set_title("Πελάτες με τις μεγαλύτερες αγορές")
    figure.tight_layout()
    figure.savefig(FIGURES / "top_customers.pdf")

# %% [markdown]
# ## 3. Regions with the most sales

# %%
regions = reports["top_regions"]
print(regions.head(10).to_string(index=False))

if not regions.empty:
    figure, axes = plt.subplots(figsize=(10, 5))
    top = regions.head(10).iloc[::-1]
    axes.barh(top["region"], top["revenue"].astype(float))
    axes.set_xlabel("Έσοδα")
    axes.set_title("Περιοχές με τις περισσότερες πωλήσεις")
    figure.tight_layout()
    figure.savefig(FIGURES / "top_regions.pdf")

# %% [markdown]
# ## 4. When sales happen

# %%
monthly = reports["sales_monthly"]
print(monthly.to_string(index=False))

if not monthly.empty:
    figure, axes = plt.subplots(figsize=(10, 4))
    axes.plot(monthly["period"], monthly["revenue"].astype(float), marker="o")
    axes.set_ylabel("Έσοδα")
    axes.set_title("Πωλήσεις ανά μήνα")
    figure.autofmt_xdate()
    figure.tight_layout()
    figure.savefig(FIGURES / "sales_monthly.pdf")

# %%
weekday = reports["sales_weekday"]
if not weekday.empty:
    names = ["Κυρ", "Δευ", "Τρι", "Τετ", "Πεμ", "Παρ", "Σαβ"]
    weekday = weekday.copy()
    weekday["label"] = weekday["weekday"].astype(int).map(lambda day: names[day])
    print(weekday.to_string(index=False))

    figure, axes = plt.subplots(figsize=(8, 4))
    axes.bar(weekday["label"], weekday["revenue"].astype(float))
    axes.set_ylabel("Έσοδα")
    axes.set_title("Πωλήσεις ανά ημέρα εβδομάδας")
    figure.tight_layout()
    figure.savefig(FIGURES / "sales_weekday.pdf")

# %% [markdown]
# ## 5. Products with the most refunds

# %%
print(reports["returns"].head(10).to_string(index=False))

# %% [markdown]
# ## 6. Sales per price range
#
# Banding uses the price charged on each line, not the product's current
# price, so a product that moved between bands is counted where it sold.

# %%
bands = reports["price_bands"]
print(bands.to_string(index=False))

if not bands.empty:
    figure, axes = plt.subplots(figsize=(8, 4))
    axes.bar(bands["band"], bands["revenue"].astype(float))
    axes.set_ylabel("Έσοδα")
    axes.set_title("Πωλήσεις ανά εύρος τιμής")
    figure.tight_layout()
    figure.savefig(FIGURES / "price_bands.pdf")

# %% [markdown]
# ## 7. Sales per product characteristic
#
# The dataset carries no structured category, only a free-text description, so
# these tags are keyword-derived. They are indicative, not authoritative, and
# the share falling in `uncategorised` is the honest measure of that limit.

# %%
characteristics = reports["characteristics"]
print(characteristics.to_string(index=False))

if not characteristics.empty:
    total = characteristics["revenue"].astype(float).sum()
    uncategorised = characteristics.loc[
        characteristics["characteristic"] == "uncategorised", "revenue"
    ]
    share = float(uncategorised.iloc[0]) / total if len(uncategorised) else 0.0
    print(f"\nUncategorised share of revenue: {share:.1%}")

    figure, axes = plt.subplots(figsize=(9, 4))
    ordered = characteristics.sort_values("revenue", ascending=True)
    axes.barh(ordered["characteristic"], ordered["revenue"].astype(float))
    axes.set_xlabel("Έσοδα")
    axes.set_title("Πωλήσεις ανά χαρακτηριστικό προϊόντος")
    figure.tight_layout()
    figure.savefig(FIGURES / "characteristics.pdf")

# %% [markdown]
# ## Consistency check
#
# Price bands and characteristics both partition revenue, so each must sum
# back to the same total. This is asserted in the test suite as well; keeping
# it visible here means a broken figure is obvious while writing.

# %%
if not bands.empty and not characteristics.empty:
    band_total = bands["revenue"].astype(float).sum()
    characteristic_total = characteristics["revenue"].astype(float).sum()
    print(f"Price bands total:      {band_total:,.2f}")
    print(f"Characteristics total:  {characteristic_total:,.2f}")
    assert abs(band_total - characteristic_total) < 0.01
    print("Both partitions agree.")
