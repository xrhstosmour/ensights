# Business metrics

GMV, repeat purchase rate, cohort retention and RFM. All measured; no
assumptions anywhere in this module. For what each of these means in plain
words and where the ideas come from, see
[product-market-fit.md](product-market-fit.md).

## Decisions worth knowing

**GMV is reported gross of refunds**, the conventional definition, with the
refunded and net values in adjacent columns. Neither figure can disappear into
the other, and a caller choosing the wrong one is doing so visibly.

**Repeat rate counts identified customers only.** Anonymous sales cannot be
tied to a person, and including them would systematically understate repeat
behaviour by treating every anonymous sale as a distinct one-time buyer.

**Recency floors, it does not round.** A customer who last bought 27 days and
9 hours ago is 27 days stale. The first draft cast straight to integer, which
rounds in PostgreSQL and reported 28; a test caught it.

**Recency is measured against the latest order in the data**, not the current
date, so results on a historical dataset stay reproducible instead of drifting
daily. Pass an explicit reference date to override.

## RFM is not a prediction

The monetary column is observed value to date. No model produced it. "Monetary"
in an RFM table is easy to misread as a lifetime-value forecast, so the schema
description, the endpoint and the thesis all say otherwise.

The same features feed the level-two [clustering](clustering.md).

## Cohort grid shape

The retention grid is triangular by construction: newer cohorts have had fewer
months to return. Empty cells at the lower right mean "not yet observable", not
"zero retention". Do not fill them.

## Revenue retention rides alongside logo retention

Each row of the cohort grid also carries `period_revenue`, `cohort_revenue`
and `revenue_retention_rate`, the same idea as the customer-count retention
above, but for the revenue that cohort produced instead of the headcount.
`cohort_revenue` is always the cohort's own first-period revenue, so
`revenue_retention_rate` is always 1.0 at `period_index` 0 by construction.

The `/cohort-shape` endpoint (`app/analysis/cohort_shape.py`) fits a trend
line through each cohort's `revenue_retention_rate` and labels it
super-linear, linear or sub-linear. It needs at least two periods after a
cohort's own acquisition month to fit anything, cohorts younger than that are
omitted from the result rather than given a forced label.
