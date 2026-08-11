# Growth accounting

Decomposes revenue change into six flows and derives the ratios that describe
whether growth is healthy. Follows the quantitative product-market-fit
framework popularised by Tribe Capital, adapted to retail.

Measured, not assumed: it needs only the transaction record.

## The six flows

Per period, each customer's revenue falls into exactly one of: **new**,
**resurrected**, **retained**, **expansion**, **contraction**, **churned**.

## The identities are the correctness test

```
revenue(t)   = retained + expansion + new + resurrected
revenue(t-1) = retained + contraction + churned
```

These are asserted directly in the tests, on synthetic data and on real
imported sales. A decomposition that does not balance is wrong by definition,
so if you change the classification logic, run those tests first and trust them
over your reasoning.

## Derived ratios

- **Quick ratio**: gains over losses. Below 1.0 total revenue is shrinking.
- **Net churn**: net loss as a fraction of previous revenue. Negative means
  the business grows without acquiring anyone.
- **Gross retention**: retained over previous revenue.

Quick ratio is `None` when nothing was lost. It is unbounded there rather than
undefined, but reporting infinity helps nobody; the flows carry the story.

## Concentration

Top decile, quintile and half shares, largest-customer share, and a Gini
coefficient.

This is the measure that catches a false positive. A store whose top two
customers produce most of its revenue behaves like a wholesaler with key
accounts however it brands itself, and no growth rate reveals that alone.

## Why there are no thresholds

The framework is business-model agnostic on purpose: a subscription store, a
one-off gift retailer and a wholesaler all emit the same six flows. That is
what lets one system serve all of them.

A fixed benchmark would not travel the same way, so none is defined. A quick
ratio of 1.0 separates growth from decline *arithmetically*, but what counts as
healthy depends on the model. Report the numbers; leave interpretation to the
reader. The framework's own authors do the same.

## Where it stops

Anonymous sales are excluded. The decomposition tracks individuals across
periods, and an unattributable sale would register as a new customer every
period, inflating both the new and churned flows.
