# Business metrics

GMV, repeat purchase rate, cohort retention and RFM. All measured; no
assumptions anywhere in this module.

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
