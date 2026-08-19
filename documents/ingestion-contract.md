# Transaction data contract

Everything the system analyses is a stream of **transaction lines**. One line
is one product inside one transaction. A merchant who can produce that shape
can be analysed without a line of code being written for them.

There are three ways to deliver it, and they are held to identical rules:

| Route | Who moves the data | Use it when |
| --- | --- | --- |
| File | You export, we read | One-off imports and historical backfills |
| API | You push | Ongoing, near-real-time delivery |
| Database | We pull | You can grant a read-only account and prefer not to build anything |

The rules live in `app/ingestion/normalisation.py` and are applied once, so no
route can quietly accept what another rejects.

## Getting a tenant and a token

Every request below needs `Authorization: Bearer <token>`. Two ways to get
one:

- **Self-service, shared tenant.** `POST /api/v1/auth/register` with `email`,
  `password`, and an optional `full_name` creates a user and returns tokens
  immediately, no admin involved. This is enough to try Route 1 against your
  own data right away, but the account lands in the shared system tenant
  alongside anyone else who registered the same way.
- **Isolated tenant.** `POST /api/v1/tenants` creates a dedicated tenant, but
  it is admin-only (`SuperuserUser`), so a real deployment for one merchant
  needs an admin to create it first. `./scripts/demo.sh` already seeds a
  superuser for this: its email and where to find its password are printed
  when the script runs, and its credentials work against `/api/v1/auth/login`
  the same way a registered user's would.

## The canonical line

| Field | Type | Required | Meaning |
| --- | --- | --- | --- |
| `order_number` | string | yes | Transaction identifier in your system. Lines sharing one belong to one transaction. |
| `ordered_at` | timestamp | yes | When the transaction took place. ISO 8601 over the API. |
| `stock_code` | string | yes | Product identifier in your system. Stable across time, this is what products are grouped by. |
| `quantity` | integer | yes | Units on the line. **Negative** when the line reverses a sale. |
| `unit_price` | decimal | yes | Price per unit **as actually charged on this line**, not the product's current price. |
| `description` | string | no | Free-text product name. Used for the keyword-based characteristic tagging. |
| `customer_identifier` | string | no | Buyer identifier. Omit for anonymous sales. |
| `region_name` | string | no | Where the sale happened, at whatever granularity you record. |
| `is_cancellation` | boolean | no | Set when you flag the whole transaction as cancelled, independently of the quantity sign. |

Three properties of this shape are deliberate and worth stating.

**Reversals are sent as you record them.** A negative quantity, a cancellation
flag, or both. Do not pre-net refunds against sales: the system stores returns
as separate rows with positive quantities, so refunded value and sold value
stay independently measurable. A netted feed cannot be un-netted later.

**Prices are per unit, as charged.** A product whose price changed over time is
counted in the price band it actually sold in. Sending today's list price
would rewrite history.

**Anonymous sales are welcome.** They stay in product, region and time
analyses and are excluded only from customer-level ones, which say so
explicitly. Dropping them instead would understate revenue.

## What is rejected, and why

A line that survives is one that can support analysis. The rest are counted by
reason rather than silently dropped, and the API names them individually.

| Reason | Meaning |
| --- | --- |
| `missing_identifier` | No `order_number` or no `stock_code`, so the line cannot be attributed. |
| `unparseable_date` | `ordered_at` matches no known layout. |
| `unparseable_quantity` | `quantity` is not a number. |
| `unparseable_price` | `unit_price` is not a number. |
| `zero_quantity` | Nothing moved. |
| `non_positive_price` | A stock adjustment or bad-debt entry rather than trade. Left in, these distort every revenue figure. |
| `non_product_code` | A code you declared administrative, for example postage, fees or manual adjustments. |

The last one deserves attention when onboarding. Most merchants record
postage, gift vouchers and manual corrections through the same line format as
merchandise. Left in, they win rankings they should not be in: in the reference
dataset, manual adjustments and postage rank first and third by revenue. Send
your own codes with the batch, or configure them on the source. They cannot be
guessed reliably: codes that look administrative are sometimes real products.
This applies uniformly across all three routes; the one exception is the
Online Retail II adapter's own gift-voucher prefix check, scoped to that
adapter alone because that dataset's voucher codes carry a variable
denomination suffix (see `NON_PRODUCT_STOCK_CODES` in
`app/ingestion/online_retail.py`) — it never affects your own data.

## Route 1: post a batch

```http
POST /api/v1/ingestion/transactions
Authorization: Bearer <token>
```

```json
{
  "source_name": "shopify-export",
  "non_product_codes": ["POSTAGE", "GIFTCARD"],
  "records": [
    {
      "order_number": "SO-1001",
      "ordered_at": "2024-03-01T10:00:00",
      "stock_code": "TEA-01",
      "quantity": 2,
      "unit_price": "4.50",
      "description": "Green tea 100g",
      "customer_identifier": "cust-88",
      "region_name": "Greece"
    }
  ]
}
```

The response reports what was created and, line by line, what was not:

```json
{
  "source_name": "shopify-export",
  "records_received": 2,
  "records_accepted": 1,
  "orders_created": 1,
  "order_items_created": 1,
  "returns_created": 0,
  "transactions_skipped": 0,
  "customers_created": 1,
  "products_created": 1,
  "regions_created": 1,
  "rejected": [{"index": 1, "order_number": "SO-1002", "reason": "zero_quantity"}]
}
```

Batches hold up to 5000 lines. Send a long history as several requests, or use
the database route instead.

**Retries are safe.** A transaction already present is skipped whole and
reported under `transactions_skipped`, so a redelivered batch cannot double
anyone's revenue. Send whole transactions per batch: splitting one transaction
across two requests imports the first part and then skips the second, because
the transaction already exists by then.

## Route 2: read from your database

Grant a read-only account and describe where the fields live. No adapter is
written per merchant. This is a Celery task, not an HTTP endpoint, so it runs
from a Python process with the project's environment loaded and a worker
running to pick it up:

```bash
# One-off, from the project root, with the worker already running
# (`uv run celery -A app.celery_app worker --loglevel=info`):
uv run --env-file .env python
```

```python
from app.ingestion.sql_source import SQLSourceConfiguration
from app.tasks.ingestion import import_sql_source_task

configuration = SQLSourceConfiguration(
    url="postgresql+psycopg://reader:secret@shop-db:5432/shop",
    query="SELECT * FROM order_lines WHERE created_at >= :since",
    parameters={"since": "2024-01-01"},
    columns={
        "order_number": "order_reference",
        "ordered_at": "created_at",
        "stock_code": "sku",
        "quantity": "units",
        "unit_price": "price_each",
        "description": "product_title",
        "customer_identifier": "buyer",
        "region_name": "shipping_country",
    },
    cancellation_prefix="CR-",
    non_product_codes=frozenset({"POSTAGE"}),
)

import_sql_source_task.delay(configuration.model_dump(mode="json"))
```

Any database SQLAlchemy can reach works, and rows stream in batches rather
than being loaded at once. The mapping is explicit on purpose: inferring
column names from their spelling works until the day it matches the wrong
column, and a wrong mapping costs far more than a missing one. A canonical
field misspelled in the mapping is an error, not an omission.

`cancellation_prefix` covers the common case of a shop marking cancellations
in the reference itself rather than in a column.

## Route 3: a file export

Implement `DataSourceAdapter` for the file layout, as
`app/ingestion/online_retail.py` does for the reference dataset. This is the
only route that needs code, and only because file layouts vary without limit.

## What the system does with a line

- Lines sharing an `order_number` become one transaction.
- A reversal, by sign or by flag, becomes a **return** with a positive
  quantity, never a negative order line.
- Customers, products and regions are created on first sight, keyed by the
  identifiers you send.
- Everything is tenant-scoped, so one deployment serves many shops.

The reasoning behind these choices is in
[methodology/ingestion.md](methodology/ingestion.md).
