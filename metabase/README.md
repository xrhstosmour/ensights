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

Set **Admin, Localization, Number separators** to `.` alone, so numbers carry
a dot for the decimal mark and no thousands separator at all: `379437.96`, not
`379,437.96`. A grouping separator is the ambiguous part here, since a dot
groups thousands in some conventions and marks the decimal in others.

On first run, Metabase asks for a database to connect to. Use the read-only
credentials `setup.sh` generated:

| Field | Value |
| --- | --- |
| Database type | PostgreSQL |
| Host | `postgresql` (the container name) |
| Port | `5432` |
| Database name | value of `POSTGRESQL_DATABASE` in `.env` |
| Username | `metabase_readonly` |
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
| `01_top_products.sql` | Top Products | `/analytics/top-products` |
| `02_top_customers.sql` | Top Customers | `/analytics/top-customers` |
| `03_top_regions.sql` | Top Regions | `/analytics/top-regions` |
| `04_sales_over_time.sql` | Sales Over Time | `/analytics/sales-over-time` |
| `05_sales_by_weekday.sql` | Sales By Weekday | `/analytics/sales-by-weekday` |
| `06_top_returned_products.sql` | Top Returns | `/analytics/top-returned-products` |
| `07_sales_by_price_band.sql` | Price Bands | `/analytics/sales-by-price-band` |
| `08_gross_merchandise_value.sql` | GMV And Refunds | `/business-metrics/gross-merchandise-value` |
| `09_cohort_retention.sql` | Cohort Retention | `/business-metrics/cohort-retention` |
| `10_rfm.sql` | RFM | `/business-metrics/rfm` |
| `11_association_rules.sql` | Association Rules | `/market-basket/rules` |
| `12_revenue_concentration.sql` | Revenue Concentration | `/growth-accounting` |

Card names are short and capitalised, and so are the column headers, which the
queries set with quoted aliases such as `AS "Stock Code"`.

Every timestamp column is rendered as ISO 8601 text, `2010-12-09T20:01:00.000`,
by the same `TO_CHAR` call in each query. One format everywhere means a date
reads the same on every card, in 24 hour time, and sorts chronologically,
because ISO 8601 sorts correctly as text. The stored columns are
`timestamp without time zone` holding UTC, so nothing is converted on the way
out and no offset is shown that could be misread as local time. Date filtering
still works on the underlying column through the `[[AND ... {{start}}]]`
clauses, which test the real timestamp rather than the formatted output. Naming them in SQL
rather than in the Metabase interface means a re-created card comes back with
the same headers instead of raw column names.

## Dashboards

Three dashboards cover the ground without duplicating cards. Splitting them
this way also keeps each board small enough to take in at a glance:

- **Sales**, 01, 03, 04, 05, 07. What sold, where and when.
- **Customers**, 02, 09, 10, 12. Who bought, whether they came back, and how
  concentrated the revenue is.
- **Merchandising**, 06, 11, 08. What came back, what sells together, and the
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

## Why forecasting and clustering are not cards either

A card is a SQL query, so a card can only show something the database already
holds. Sales, returns, customers and regions are facts in the schema, and so
are the mined itemsets and association rules, because the mining task writes
its results back into `frequent_itemsets` and `association_rules`.

Forecasts, customer segments, growth flows and unit economics are not facts in
the schema. They are outputs of models that run in Python at request time,
using statsmodels and scikit-learn, and nothing persists them. Reproducing a
Holt-Winters forecast or a k-means segmentation in SQL would mean
reimplementing the model in a second language, where it would drift from the
one the thesis actually evaluates.

So they stay where they are computed:

| Question | Where to read it |
| --- | --- |
| Revenue forecast against a naive baseline | `GET /api/v1/forecasting/revenue` |
| Nested customer and region segments | `GET /api/v1/segmentation` |
| Revenue split into new, retained and churned | `GET /api/v1/growth-accounting` |
| LTV, CAC and sensitivity grids | `GET /api/v1/profitability/*` |

The notebooks under `notebooks/` read the same endpoints and models when a
figure for the manuscript is needed.

## Keeping cards honest

The queries are verified against a migrated database, and the ones with
non-trivial logic are cross-checked against the API on seeded data, so a card
and its endpoint return the same numbers. If you change a card, re-check it
against its endpoint rather than trusting that it still agrees.
