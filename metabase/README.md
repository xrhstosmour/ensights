# Metabase dashboards

Ready-made SQL cards over the canonical schema, for merchants who want the
insights without calling the API.

Every card here mirrors an endpoint, and deliberately so: the dashboard and the
API must never disagree about a number. Where a card's logic looks fussy, it is
usually reproducing a decision documented in `documents/roadmap.md`, and the
comment at the top of the file says which.

## Setup

Metabase runs as an optional service and is already wired up:

```bash
./scripts/setup.sh          # provisions the read-only database user
docker compose up metabase  # http://localhost:3000
```

On first run, Metabase asks for a database to connect to. Use the read-only
credentials `setup.sh` generated:

| Field | Value |
| --- | --- |
| Database type | PostgreSQL |
| Host | `postgresql` (the container name) |
| Port | `5432` |
| Database name | value of `POSTGRESQL_DATABASE` in `.env` |
| Username | `metabase_read_only` |
| Password | value of `METABASE_READ_ONLY_PASSWORD` in `.env` |

The read-only user is the point: a dashboard should never be able to write to
the analytical schema, however a query is edited later.

## Adding the cards

Metabase has no import format for raw SQL, so each card is created once by
hand:

1. **New** → **SQL query**, pick the database above.
2. Paste the contents of a file from `queries/`.
3. Save it under the name in the table below.
4. Add it to a dashboard.

The `[[AND ... {{start}}]]` blocks are Metabase's optional-clause syntax. When
you save a card containing them, Metabase offers to create `start` and `end`
date filters; accept, and the clause is only applied when a value is supplied.

## The cards

| File | Card | Mirrors |
| --- | --- | --- |
| `01_top_products.sql` | Products with the highest sales | `/analytics/top-products` |
| `02_top_customers.sql` | Customers with the most purchases | `/analytics/top-customers` |
| `03_top_regions.sql` | Regions with the most sales | `/analytics/top-regions` |
| `04_sales_over_time.sql` | When sales happen | `/analytics/sales-over-time` |
| `05_sales_by_weekday.sql` | Which weekdays sell most | `/analytics/sales-by-weekday` |
| `06_top_returned_products.sql` | Products with the most refunds | `/analytics/top-returned-products` |
| `07_sales_by_price_band.sql` | Sales per price range | `/analytics/sales-by-price-band` |
| `08_gross_merchandise_value.sql` | GMV, refunds and net value | `/business-metrics/gross-merchandise-value` |
| `09_cohort_retention.sql` | Acquisition cohorts and retention | `/business-metrics/cohort-retention` |
| `10_rfm.sql` | Recency, frequency, monetary | `/business-metrics/rfm` |
| `11_association_rules.sql` | Products bought together | `/market-basket/rules` |
| `12_revenue_concentration.sql` | Revenue concentration | `/growth-accounting` |

## Suggested dashboards

Three dashboards cover the ground without duplicating cards:

- **Sales** — 01, 03, 04, 05, 07. What sold, where and when.
- **Customers** — 02, 09, 10, 12. Who bought, whether they came back, and how
  concentrated the revenue is.
- **Merchandising** — 06, 11, 08. What came back, what sells together, and the
  headline value.

## Reading the cards honestly

Three cards are easy to misread, and the comments in the files say so too:

- **`08` reports GMV gross of refunds**, with the refunded and net columns
  beside it. Quoting the gross column alone overstates what the business keeps.
- **`10` monetary is observed value to date, not predicted lifetime value.**
  No model produced it.
- **`11` filters to lift ≥ 1.0.** Support and confidence alone will promote a
  rule whose right-hand side is simply a popular product.

There is no profitability card. That is deliberate: the schema holds no cost of
goods and no marketing spend, so profitability cannot be measured from it. The
`/profitability` endpoints answer that question as an explicit scenario over
stated assumptions, and a dashboard tile stripped of those assumptions would be
exactly the misreading the rest of the project works to avoid.

## Keeping cards honest

The queries are verified against a migrated database, and the ones with
non-trivial logic are cross-checked against the API on seeded data, so a card
and its endpoint return the same numbers. If you change a card, re-check it
against its endpoint rather than trusting that it still agrees.
