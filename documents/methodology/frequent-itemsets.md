# Frequent itemsets

Market basket analysis: which products genuinely co-occur.

Both classical algorithms are available. Apriori generates candidates level by
level; FP-Growth builds a prefix tree and avoids candidate generation. **For
the same threshold they produce identical itemsets**, so the choice is runtime,
not result. A test asserts that equivalence, and the comparison is itself a
thesis experiment.

## Basket construction

A basket is the set of distinct products in one order. Two normalisations
happen first:

- **Duplicate lines collapse.** Co-occurrence is binary; buying two of the same
  product adds no information.
- **One-item baskets are dropped.** They cannot contribute to any pair, and in
  retail they are numerous. Excluding them sharpens support values rather than
  distorting them, because the denominator stops counting transactions that
  could never have contributed.

## Lift is the metric that matters

Support and confidence alone will happily promote a rule whose right-hand side
is simply a popular product: if nearly every basket contains it, it follows
everything with high confidence and tells you nothing.

Lift above 1.0 means the two sides co-occur more than independence predicts.
The API filters to lift ≥ 1.0 by default. Keep that default.

## Persistence

Runs are materialised, not recomputed per request. Both tables store the
algorithm and thresholds, because **a support value is meaningless without the
threshold it was mined at**. Product descriptions are resolved once at write
time so reads need no join.

## Where it stops

Mining is O(baskets × items) in the worst case. On dense data, cap
`maximum_itemset_size` before raising the support threshold: the cap bounds
runtime without discarding the pairs that carry most of the interpretable
signal.
