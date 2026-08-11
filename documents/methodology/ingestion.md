# Ingestion

Turns any source of transaction lines into the canonical schema.

The merchant-facing version of this, the field-by-field format and the three
delivery routes, is [documents/ingestion-contract.md](../ingestion-contract.md).
This note covers why it is shaped that way.

## The contract

`DataSourceAdapter.fetch()` yields `CanonicalRecord` values. That is the whole
interface. Three adapters ship: a CSV export, an in-memory sequence behind the
posting endpoint, and a configuration-driven SQL reader that needs a query and
a column mapping rather than code. No analytical code changes for any of them.

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

These rules live in `app/ingestion/normalisation.py`, not in the adapters. A
rule implemented once per source is a rule that eventually differs per source,
and then two merchants sending the same data get different answers.

Rows with no customer identifier are **kept**. Roughly a quarter of the Online
Retail II dataset has none. They are real sales and belong in product, region
and time analyses; only the customer-level analyses exclude them, and each
does so explicitly.

## Extending it

Most sources need no code at all: push a batch to the API, or point the SQL
reader at the merchant's database with a column mapping. Write an adapter only
for a file layout nothing else can express, and register nothing. If your
source has real product categories, feed them through rather than relying on
the keyword tagging described in
[descriptive analytics](descriptive-analytics.md).

The SQL reader is tested against a SQLite database whose schema, column names
and engine share nothing with the CSV export the results chapters use. That is
the point of the test: generality claimed from design is an argument,
generality exercised on an unrelated source is evidence.

## Where it stops

The canonical schema has one geographic level. A source reporting city and
country collapses to whichever you map to `region_name`. Adding a hierarchy
means a self-referencing parent on `Region`, which no analytical code would
need to know about.
