# Ensights

Master's thesis project, National and Kapodistrian University of Athens,
Department of Informatics and Telecommunications: **"Extraction of
Intelligent Analytics from E-Commerce Data"**.

A FastAPI backend that turns raw e-commerce transactions into business
intelligence: frequent itemsets, customer segmentation, revenue forecasting,
growth accounting, and unit economics, exposed through a REST API and a set
of Metabase dashboards. The manuscript itself lives in [`thesis/`](thesis/),
built from the same code and data this repository runs.

## What this actually does, in plain words

An online shop already records every sale it makes. That record is usually
just a long list of lines: this invoice, this product, this many units, at
this price, on this date, to this customer, in this country. On its own the
list answers nothing, because nobody can read a million lines.

Ensights reads that list and answers the questions the shop actually asks.
It works in three steps.

**1. Bring the data in.** The shop sends its sales, either by posting them to
the API, by letting the system read its database, or by exporting a file.
Whatever the original format, every line is converted into one common shape,
so the analysis never has to know which shop it came from. That common shape
is written down as a contract in
[`documents/ingestion-contract.md`](documents/ingestion-contract.md).

**2. Store it as facts.** The lines become customers, products, regions,
orders, order lines and returns in a PostgreSQL database. Nothing is
pre-summarised and refunds are kept separate from sales, so no figure is
silently baked in and later impossible to take apart.

**3. Answer questions about it.** Some answers are simple counting, like which
products sold most. Others need data mining or statistics, like which products
tend to be bought together, which customers behave alike, or what revenue
might look like next month.

There are then three ways to read the answers, and they are for three
different audiences:

| Surface | Who it is for | What it gives |
| --- | --- | --- |
| **REST API** (`/api/v1/...`) | Another program, or anyone clicking through Swagger | Every answer as JSON, including the ones that come from models |
| **Metabase dashboards** | A shop owner who does not write code | Tables and charts over the stored facts, refreshed by reloading |
| **Jupyter notebooks** (`notebooks/`) | The thesis itself | The experiments and the figures printed in the manuscript |

They are not three copies of the logic. Metabase reads the same database with
a read only account, and a card and its matching endpoint are required to
return the same number. The notebooks call the same code the API calls.

One deliberate limit is worth saying out loud, because it is the honest part
of the work. The dataset contains no cost of goods and no marketing spend, so
the system cannot measure whether the shop is profitable. The profitability
endpoints therefore return a scenario built on assumptions that are stated in
the response itself, never a measurement, and every response carries that
disclaimer with it.

## Setup & run

Needs [uv](https://docs.astral.sh/uv/getting-started/installation/) and
[Docker](https://docs.docker.com/engine/install/).

```bash
./scripts/setup.sh  # first time only
./scripts/demo.sh   # every time after
```

`demo.sh` starts every service (Postgres, Redis, RabbitMQ, Metabase), applies
migrations, seeds demo data, prints the API and Metabase URLs plus the demo
login, then runs the API server in the foreground. `Ctrl+C` stops the API
server, the containers keep running.

## Adding data

The platform isn't tied to the Online Retail II dataset used in the thesis.
Three ways to bring your own:

1. **Push a batch**, `POST /api/v1/ingestion/transactions` with up to 5000
   lines. No code needed.
2. **Point at a database**, describe which columns hold which field, a
   background task streams rows in from any database SQLAlchemy can reach.
   No adapter to write, but it runs as a Celery task, not an HTTP call.
3. **Write a file adapter**, for a layout that doesn't fit the above, the
   way `app/ingestion/online_retail.py` does for the reference dataset.

Full field-by-field rules are in
[`documents/ingestion-contract.md`](documents/ingestion-contract.md).

## Where to watch the results

- **Swagger UI**, [http://localhost:8000/try](http://localhost:8000/try):
  every endpoint below, with "Try it out".
- **Metabase**, URL printed by `demo.sh`: 12 SQL cards mirroring the API
  one-to-one, added by hand into 3 suggested dashboards (setup notes in
  [`metabase/README.md`](metabase/README.md)).

| Endpoint prefix | What it answers |
| --- | --- |
| `/api/v1/analytics` | Sales by product, region, time, price band. |
| `/api/v1/business-metrics` | GMV, repeat-purchase rate, cohort retention, RFM. |
| `/api/v1/segmentation` | Customer clustering (region/time, then RFM). |
| `/api/v1/market-basket` | Frequent itemset mining and association rules. |
| `/api/v1/forecasting` | Revenue forecasts vs. a naive baseline. |
| `/api/v1/growth-accounting` | Revenue decomposed into new/retained/churned flows. |
| `/api/v1/profitability` | LTV, CAC, and unit-economics sensitivity grids. |

The reasoning and sourcing behind these are documented in
[`documents/methodology/`](documents/methodology/).

## The answers that only the API can give

Sales, returns and mined itemsets are stored in the database, so a Metabase
card can show them. Forecasts and segments are not stored: they are produced
by models that run when the request arrives, so they are read from the API.
`metabase/README.md` explains the split. All four examples below are real
responses over the full Online Retail II dataset, abridged.

**Revenue forecast, compared against a naive baseline.** The comparison is the
point. A model that cannot beat "next month looks like this month" has proved
nothing, so the baseline and the skill score are always reported, including
when the skill score is negative:

```bash
curl -H "Authorization: Bearer $TOKEN" \
  "http://localhost:8000/api/v1/forecasting/revenue?horizon=3"
```

```json
{
  "method": "exponential_smoothing",
  "horizon": 3,
  "history_length": 25,
  "forecast": [587222.83, 502905.56, 671261.41],
  "metrics": {"mean_absolute_error": 419623.67, "mean_absolute_percentage_error": 51.12},
  "baseline_metrics": {"mean_absolute_error": 346864.32},
  "skill_score": -0.21
}
```

**Nested customer segmentation.** Countries are clustered first, then each
cluster is split again on purchasing behaviour. The silhouette score for every
candidate number of clusters is returned, so the choice of `chosen_k` can be
checked rather than trusted:

```json
{"chosen_k": 2, "silhouette": 0.875,
 "scores": {"2": 0.875, "3": 0.716, "4": 0.687, "5": 0.664},
 "clusters": [{"label": "1", "level": 1, "size": 39, "members": ["Australia", "Austria", "..."]}]}
```

**Growth accounting.** Each month's revenue is decomposed into where it came
from, so a flat total that hides equal churn and acquisition cannot look
healthy:

```json
{"period": "2010-01-01T00:00:00", "revenue": 524504.67,
 "new": 156527.47, "retained": 265475.35, "expansion": 102501.85,
 "contraction": 130293.16, "churned": 270131.82,
 "gross_retention_rate": 0.399, "quick_ratio": 0.647}
```

**Unit economics.** Note the disclaimer travelling with the numbers. The
dataset has no costs and no marketing spend, so this is a scenario over stated
assumptions and the response says so itself:

```json
{"average_customer_revenue": 2046.66, "lifetime_value": 1023.33,
 "assumptions": {"gross_margin": 0.5, "customer_acquisition_cost": 0.0},
 "disclaimer": "Scenario output, not a measurement. The source data contains no cost of goods and no marketing spend, so these figures follow from the stated assumptions and hold only insofar as those assumptions do."}
```

## Reproducing the thesis figures

The manuscript's numbers come from this code and the public dataset, so they
can be checked. Importing Online Retail II and calling
`/api/v1/business-metrics/customer-summary` returns 4234 repeat customers
against 1618 one time customers, a repeat purchase rate of 72.4%, 6.25 orders
per customer and an average order value of 493.63, which are the figures
quoted in chapter 7.

## Exporting the thesis PDF

```bash
./scripts/export-thesis.sh          # needs local XeLaTeX + biber
./scripts/export-thesis.sh --docker # or build inside a TeX Live container
```

Output: `documents/<author>-thesis.pdf`, the file to hand over.

## License

MIT License, see [LICENSE](LICENSE) file.
