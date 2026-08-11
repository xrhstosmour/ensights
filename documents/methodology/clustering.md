# Clustering

The nested tree the thesis supervisor asked for: cluster on the parameters
that matter most, then cluster again *within* each group on additional
parameters.

- **Level one**: regions, by revenue, orders, customers and active months.
- **Level two**: the customers inside each region group, by RFM.

## Standardisation is not optional

Features are standardised before clustering. Without it, a currency-scaled
feature dominates a count-scaled one purely through its units, and k-means
clusters on units rather than on behaviour.

There is a test where the real structure lives entirely in a small-scale
feature and a large-scale one carries only noise. It fails without scaling.
Do not remove it.

## k is chosen, not assumed

Every candidate k is scored by silhouette and the best kept. All the scores are
returned so the thesis can tabulate evidence rather than assert a number.

## Why `active_months` is in the level-one features

It is what makes the first level spatio-*temporal* rather than merely spatial.
Two regions with equal revenue are genuinely different markets if one earned it
steadily across the year and the other in a single month.

## Honest degradation

- Too few rows to partition meaningfully: one cluster, no silhouette. Inventing
  structure the data cannot support would be worse than saying so.
- Customers with no region are excluded from a region-rooted tree rather than
  forced into an arbitrary branch. They remain visible through the flat RFM
  endpoint.

## Reproducibility

The seed is fixed and clusters are ordered by size, so labels stay stable
enough to discuss across runs and the write-up's numbers can be regenerated.
