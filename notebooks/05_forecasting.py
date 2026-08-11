"""Sales forecasting with an honest backtest.

Backs the forecasting half of chapter 7. Every model is measured against a
naive last-value baseline, because a forecast that cannot beat "next month
looks like this month" has demonstrated nothing.

    uv run python notebooks/05_forecasting.py
"""

# %%
from __future__ import annotations

import asyncio
from pathlib import Path

import matplotlib
import matplotlib.pyplot as plt
import pandas as pd

from app.analysis.forecasting import EXPONENTIAL_SMOOTHING
from app.analysis.forecasting import NAIVE
from app.analysis.forecasting import forecast
from app.analysis.forecasting import summarise
from app.database import async_session_factory
from app.services.forecasting_service import ForecastingService

matplotlib.use("Agg")

FIGURES = Path(__file__).resolve().parent.parent / "thesis" / "figures"
FIGURES.mkdir(parents=True, exist_ok=True)

HORIZON = 3


# %%
async def load_series() -> tuple[list, list[float]]:
    """Load the monthly net revenue series.

    Returns:
        Period labels and their net values.
    """
    async with async_session_factory() as session:
        return await ForecastingService(session).revenue_series("month")


periods, values = asyncio.run(load_series())
series = pd.Series(values, index=pd.to_datetime(periods))
print(f"observations: {len(series)}")
print(series.round(2).to_string())

# %% [markdown]
# ## Comparing methods on the same holdout
#
# Both are fitted only on the data before the holdout, so the errors describe
# points the model never saw.

# %%
rows = []
for method in (NAIVE, EXPONENTIAL_SMOOTHING):
    result = forecast(values, horizon=HORIZON, method=method, seasonal_periods=12)
    summary = summarise(result)
    metrics = summary["metrics"] or {}
    rows.append({
        "method": method,
        "MAE": metrics.get("mean_absolute_error"),
        "RMSE": metrics.get("root_mean_squared_error"),
        "MAPE": metrics.get("mean_absolute_percentage_error"),
        "skill_score": summary["skill_score"],
    })

comparison = pd.DataFrame(rows)
print(comparison.to_string(index=False))

# %% [markdown]
# A positive skill score means the model beat the naive baseline. A negative
# one means it did worse, and is reported as such rather than hidden.

# %%
result = forecast(values, horizon=HORIZON, method=EXPONENTIAL_SMOOTHING,
                  seasonal_periods=12)

future_index = pd.date_range(series.index[-1], periods=HORIZON + 1, freq="MS")[1:]
projection = pd.Series(result.forecast, index=future_index)

figure, axes = plt.subplots(figsize=(11, 4))
axes.plot(series.index, series.values, marker="o", label="Ιστορικό")
axes.plot(projection.index, projection.values, marker="o", linestyle="--",
          label="Πρόβλεψη")
axes.set_ylabel("Καθαρή αξία πωλήσεων")
axes.set_title("Πρόβλεψη μηνιαίων πωλήσεων")
axes.legend()
figure.autofmt_xdate()
figure.tight_layout()
figure.savefig(FIGURES / "revenue_forecast.pdf")

print("\nforecast:")
print(projection.round(2).to_string())

# %% [markdown]
# ## A caution on the final period
#
# Datasets of this kind frequently end mid-month, leaving the last observation
# artificially low. If the final point sits far below its neighbours, treat it
# as truncated rather than as a decline, and consider excluding it before
# fitting.

# %%
if len(series) >= 3:
    tail_ratio = series.iloc[-1] / series.iloc[-4:-1].mean()
    print(f"final period against the previous three: {tail_ratio:.2f}")
    if tail_ratio < 0.6:
        print("The final period looks truncated rather than genuinely weak.")
