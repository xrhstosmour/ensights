# Ensights

Master's thesis project — National and Kapodistrian University of Athens,
Department of Informatics and Telecommunications: **"Extraction of
Intelligent Analytics from E-Commerce Data"**.

A FastAPI backend that turns raw e-commerce transactions into business
intelligence: frequent itemsets, customer segmentation, revenue forecasting,
growth accounting, and unit economics, exposed through a REST API and a set
of Metabase dashboards. The manuscript itself lives in [`thesis/`](thesis/),
built from the same code and data this repository runs.

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
Three ways to bring your own, no code required for the first two:

1. **Push a batch** — `POST /api/v1/ingestion/transactions` with up to 5000
   lines.
2. **Point at a database** — describe which columns hold which field, a
   background task streams rows in from any database SQLAlchemy can reach.
3. **Write a file adapter** — for a layout that doesn't fit the above, the
   way `app/ingestion/online_retail.py` does for the reference dataset.

Full field-by-field rules are in
[`documents/ingestion-contract.md`](documents/ingestion-contract.md).

## Where to watch the results

- **Swagger UI** — [http://localhost:8000/try](http://localhost:8000/try):
  every endpoint below, with "Try it out".
- **Metabase** — URL printed by `demo.sh`: 12 pre-built dashboards mirroring
  the API one-to-one (setup notes in
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

## Exporting the thesis PDF

```bash
./scripts/export-thesis.sh          # needs local XeLaTeX + biber
./scripts/export-thesis.sh --docker # or build inside a TeX Live container
```

Output: `documents/<author>-thesis.pdf`, the file to hand over.

## License

MIT License — see [LICENSE](LICENSE) file.
