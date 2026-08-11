"""Nested region-then-customer clustering.

Backs chapter 6. Level one groups regions by their sales behaviour over time,
level two re-clusters the customers inside each of those groups by RFM.

    uv run python notebooks/04_clustering.py
"""

# %%
from __future__ import annotations

import asyncio
from pathlib import Path

import matplotlib
import matplotlib.pyplot as plt
import pandas as pd

from app.analysis.clustering import flatten
from app.analysis.clustering import partition
from app.database import async_session_factory
from app.services.segmentation_service import CUSTOMER_FEATURES
from app.services.segmentation_service import REGION_FEATURES
from app.services.segmentation_service import SegmentationService

matplotlib.use("Agg")

FIGURES = Path(__file__).resolve().parent.parent / "thesis" / "figures"
FIGURES.mkdir(parents=True, exist_ok=True)


# %%
async def load() -> tuple[list[dict], dict[str, list[dict]], object]:
    """Build both feature sets and run the nested segmentation.

    Returns:
        Region features, customer features per region, and the tree.
    """
    async with async_session_factory() as session:
        service = SegmentationService(session)
        regions = await service.region_features()
        customers = await service.customer_features_by_region()
        tree = await service.run()
        return regions, customers, tree


regions, customers_by_region, tree = asyncio.run(load())

region_frame = pd.DataFrame(regions)
print(f"regions: {len(region_frame)}")
print(region_frame.sort_values("revenue", ascending=False).head(10).to_string(index=False))

# %% [markdown]
# ## Choosing k by silhouette
#
# The number of clusters is not fixed in advance. Every candidate is scored and
# the best kept; the scores are shown so the choice is evidence rather than
# assertion.

# %%
level_one = partition(regions, REGION_FEATURES)
print("chosen k:", level_one.chosen_k)
print("silhouette:", round(level_one.silhouette or 0, 4))
scores = pd.Series(level_one.scores).sort_index()
print(scores.round(4).to_string())

figure, axes = plt.subplots(figsize=(8, 4))
axes.plot(scores.index, scores.values, marker="o")
axes.axvline(level_one.chosen_k, color="red", linestyle="--", label="επιλεγμένο k")
axes.set_xlabel("Πλήθος συστάδων (k)")
axes.set_ylabel("Δείκτης περιγράμματος")
axes.set_title("Επιλογή του k στο πρώτο επίπεδο")
axes.legend()
figure.tight_layout()
figure.savefig(FIGURES / "silhouette_level_one.pdf")

# %% [markdown]
# ## The tree

# %%
for node in tree.clusters:
    means = {name: round(value, 1) for name, value in node.feature_means.items()}
    print(f"[{node.label}] level {node.level}  size={node.size}  {means}")
    print(f"      members: {', '.join(sorted(node.members)[:8])}"
          f"{' ...' if len(node.members) > 8 else ''}")
    for child in node.children:
        child_means = {n: round(v, 1) for n, v in child.feature_means.items()}
        print(f"    [{child.label}] size={child.size}  {child_means}")

print(f"\ntotal nodes: {len(flatten(tree.clusters))}")

# %% [markdown]
# ## Customer segments within the largest region group
#
# The level-two features are RFM. Interpreting a sub-cluster means reading its
# feature means: low recency with high frequency and value is a loyal segment,
# high recency with low frequency is a lapsed one.

# %%
largest = max(tree.clusters, key=lambda node: node.size)
pooled = [row for member in largest.members
          for row in customers_by_region.get(member, [])]

if pooled:
    frame = pd.DataFrame(pooled)
    print(f"customers pooled under [{largest.label}]: {len(frame):,}")
    print(frame[list(CUSTOMER_FEATURES)].describe().round(2).to_string())

    if largest.children:
        summary = pd.DataFrame([
            {"cluster": child.label, "size": child.size, **{
                name: round(value, 2) for name, value in child.feature_means.items()}}
            for child in largest.children
        ])
        print("\n", summary.to_string(index=False))

        figure, axes = plt.subplots(figsize=(8, 5))
        axes.scatter(frame["recency_days"], frame["monetary"].clip(upper=frame["monetary"].quantile(0.99)),
                     s=8, alpha=0.4)
        axes.set_xlabel("Προσφατότητα (ημέρες)")
        axes.set_ylabel("Χρηματική αξία")
        axes.set_title(f"Πελάτες της συστάδας [{largest.label}]")
        figure.tight_layout()
        figure.savefig(FIGURES / "rfm_scatter.pdf")
