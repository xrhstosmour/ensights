"""Market basket analysis: which products are genuinely bought together.

Backs chapter 5. Compares Apriori and FP-Growth on the same baskets, which is
itself one of the thesis experiments: for a given support threshold the two
must agree on the itemsets and differ only in runtime.

    uv sync --extra analysis
    uv run python notebooks/03_frequent_itemsets.py
"""

# %%
from __future__ import annotations

import asyncio
import time
from pathlib import Path

import matplotlib
import matplotlib.pyplot as plt
import pandas as pd

from app.analysis.frequent_itemsets import APRIORI
from app.analysis.frequent_itemsets import FPGROWTH
from app.analysis.frequent_itemsets import mine
from app.database import async_session_factory
from app.services.market_basket_service import MarketBasketService

matplotlib.use("Agg")

FIGURES = Path(__file__).resolve().parent.parent / "thesis" / "figures"
FIGURES.mkdir(parents=True, exist_ok=True)

MINIMUM_SUPPORT = 0.02
MINIMUM_CONFIDENCE = 0.3


# %%
async def load_baskets() -> list[list[str]]:
    """Build the baskets once, so both algorithms see identical input.

    Returns:
        One list of stock codes per qualifying order.
    """
    async with async_session_factory() as session:
        return await MarketBasketService(session).build_baskets()


baskets = asyncio.run(load_baskets())
sizes = pd.Series([len(basket) for basket in baskets])

print(f"baskets: {len(baskets):,}")
print(sizes.describe().round(2).to_string())

# %% [markdown]
# ## Basket size distribution
#
# One-item baskets are already excluded: they cannot contribute to any
# co-occurrence, and leaving them in would only inflate the support
# denominator.

# %%
figure, axes = plt.subplots(figsize=(9, 4))
axes.hist(sizes.clip(upper=60), bins=59)
axes.set_xlabel("Πλήθος διακριτών προϊόντων ανά καλάθι")
axes.set_ylabel("Πλήθος καλαθιών")
axes.set_title("Κατανομή μεγέθους καλαθιού")
figure.tight_layout()
figure.savefig(FIGURES / "basket_sizes.pdf")

# %% [markdown]
# ## Apriori against FP-Growth
#
# Same baskets, same threshold. The itemsets must match exactly; only the
# elapsed time should differ.

# %%
timings: dict[str, float] = {}
results = {}
for algorithm in (APRIORI, FPGROWTH):
    started = time.time()
    results[algorithm] = mine(
        baskets,
        algorithm=algorithm,
        minimum_support=MINIMUM_SUPPORT,
        minimum_confidence=MINIMUM_CONFIDENCE,
    )
    timings[algorithm] = time.time() - started
    print(f"{algorithm:22} {timings[algorithm]:7.2f}s  "
          f"itemsets={len(results[algorithm].itemsets):5d}  "
          f"rules={len(results[algorithm].rules):5d}")

apriori_sets = {itemset.items for itemset in results[APRIORI].itemsets}
fpgrowth_sets = {itemset.items for itemset in results[FPGROWTH].itemsets}
print("\nidentical itemsets:", apriori_sets == fpgrowth_sets)
print(f"speed-up of FP-Growth: {timings[APRIORI] / timings[FPGROWTH]:.2f}x")

# %% [markdown]
# ## Strongest rules by lift
#
# Lift, not confidence, is the column to read. A rule whose right-hand side is
# simply a popular product scores high confidence while saying nothing.

# %%
rules = pd.DataFrame(
    [
        {
            "antecedents": ", ".join(rule.antecedents),
            "consequents": ", ".join(rule.consequents),
            "support": round(rule.support, 4),
            "confidence": round(rule.confidence, 4),
            "lift": round(rule.lift, 3),
        }
        for rule in results[FPGROWTH].rules
    ]
)

if not rules.empty:
    print(rules.head(20).to_string(index=False))

    figure, axes = plt.subplots(figsize=(8, 5))
    axes.scatter(rules["support"], rules["confidence"],
                 c=rules["lift"], cmap="viridis", alpha=0.7)
    axes.set_xlabel("Υποστήριξη")
    axes.set_ylabel("Εμπιστοσύνη")
    axes.set_title("Κανόνες συσχέτισης, χρωματισμένοι κατά άρση")
    figure.colorbar(axes.collections[0], ax=axes, label="Άρση")
    figure.tight_layout()
    figure.savefig(FIGURES / "association_rules.pdf")

# %% [markdown]
# ## Sensitivity to the support threshold
#
# The threshold is not a neutral knob: it decides what "frequent" means, and
# the count of surviving itemsets falls away sharply as it rises.

# %%
sweep = []
for support in (0.01, 0.015, 0.02, 0.03, 0.05):
    started = time.time()
    result = mine(baskets, algorithm=FPGROWTH, minimum_support=support,
                  minimum_confidence=MINIMUM_CONFIDENCE)
    sweep.append({
        "minimum_support": support,
        "itemsets": len(result.itemsets),
        "rules": len(result.rules),
        "seconds": round(time.time() - started, 2),
    })

sweep_frame = pd.DataFrame(sweep)
print(sweep_frame.to_string(index=False))

figure, axes = plt.subplots(figsize=(8, 4))
axes.plot(sweep_frame["minimum_support"], sweep_frame["itemsets"], marker="o")
axes.set_xlabel("Ελάχιστη υποστήριξη")
axes.set_ylabel("Πλήθος συχνών υποσυνόλων")
axes.set_title("Ευαισθησία στο κατώφλι υποστήριξης")
figure.tight_layout()
figure.savefig(FIGURES / "support_sensitivity.pdf")
