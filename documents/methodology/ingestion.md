# Ingestion

Turns any source of transaction lines into the canonical schema.

## The contract

`DataSourceAdapter.fetch()` yields `CanonicalRecord` values. That is the whole
interface. Supporting a new merchant means writing one adapter; no analytical
code changes.

Adapters stay deliberately stupid. They pass the source's quantity sign
through untouched rather than deciding what a negative means, because
`IngestionService` owns that interpretation and must apply it identically to
every source. An adapter that "helpfully" normalised signs would make two
sources behave differently for the same data.

Adapters stream. Real exports run to millions of rows, and the service batches
on its own terms.

## What the service decides

- A `C`-prefixed invoice, or one whose lines are all negative, becomes returns
  with no order.
- A negative line inside an otherwise normal invoice becomes a return linked
  back to that order.
- Transactions already present are skipped whole, so re-running an import is
  safe and adds only what is new.

Returns are separate rows with positive quantities, never negative order
lines. This is the single most consequential modelling decision in the project:
it makes it structurally impossible to net refunds out of revenue by accident.

## Cleaning decisions

Rows are dropped, with a counted reason, when they cannot support analysis:
unparseable date or quantity, missing product code, zero quantity, or a
non-positive price. Non-positive prices are dropped because the dataset uses
them for stock adjustments and bad-debt entries rather than trade.

Rows with no customer identifier are **kept**. Roughly a quarter of the Online
Retail II dataset has none. They are real sales and belong in product, region
and time analyses; only the customer-level analyses exclude them, and each
does so explicitly.

## Extending it

Write an adapter, register nothing. Map the source's columns onto
`CanonicalRecord` and let the service do the rest. If your source has real
product categories, feed them through rather than relying on the keyword
tagging described in [descriptive analytics](descriptive-analytics.md).

## Where it stops

The canonical schema has one geographic level. A source reporting city and
country collapses to whichever you map to `region_name`. Adding a hierarchy
means a self-referencing parent on `Region`, which no analytical code would
need to know about.
