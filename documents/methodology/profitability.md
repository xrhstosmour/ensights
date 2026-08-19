# Profitability

**This module computes scenarios, never measurements.** Everything else in the
project sits on the other side of that line.

## Why

The transaction record says what was sold and for how much. It contains no cost
of goods and no marketing spend. Profitability therefore cannot be measured
from it, and any figure claiming otherwise would be an invention dressed as a
finding.

What can be done honestly is sensitivity analysis: state the assumptions
explicitly, vary them, and report what follows *if* they hold.

## How the quarantine is enforced

- Separate module, separate service, separate endpoints.
- **Every result carries a `disclaimer` field and the assumptions that produced
  it**, through the module, the service, each API response and each sweep row.
  Tests assert this on every output path.
- No Metabase card. A dashboard tile stripped of its assumptions is exactly the
  misreading this design prevents.

If you add an output path, carry the disclaimer through it.

## LTV is gross profit, not revenue

Comparing revenue against acquisition cost overstates the ratio by exactly the
cost of goods. It is the most common way this number is inflated. A test shows
the same inputs would read 10.0 instead of the correct 4.0.

## The sweep is the headline

A single scenario invites being read as a prediction. The grid makes the
dependence on assumptions visible.

A test asserts that identical observed data flips from passing to failing the
3:1 benchmark on the assumed margin alone. **That flip is the finding**, not an
edge case: it is what the reader is supposed to take away.

## Undefined stays undefined

No acquisition cost gives a `None` ratio, not infinity. No customer lifespan
gives a `None` payback, not a guess. A scenario that never breaks even reports
`None`, not the last period.

## Benchmarks are footnotes, not literature

The 3:1 ratio, the 6-12 month payback and the 15-85% margin bands are
practitioner estimates. They bound plausible inputs; they are not findings
about this business. The thesis cites them as a footnoted industry estimate and
keeps them out of the bibliography.
