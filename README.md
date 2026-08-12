# Ensights

Generic e-commerce business intelligence platform: data mining and machine learning driven marketing/sales insights (frequent itemsets, clustering, forecasting, unit economics).

## Features

### Authentication & Authorization

- **User Authentication**: JWT-based with access + refresh tokens, OAuth2 form login
- **API Keys**: Scoped programmatic access
- **Multi-tenancy**: Tenant isolation with full CRUD (admin), system tenant fallback
- **TOTP 2FA**: Time-based one-time passwords with encrypted secrets, recovery codes, rate limiting, and replay prevention
- **Email Verification**: Redis-backed single-use tokens (24h TTL)
- **Password Reset**: Redis-backed single-use tokens (1h TTL), invalidates all sessions on reset
- **Google OAuth**: Multi-provider OAuth 2.0 login (Google, Apple, Microsoft via `OAuthProvider` enum)
- **Soft Deletes**: Recoverable data via `deleted_at` timestamps
- **Graveyard**: Centralized tombstone tracking for all deletions
- **Audit Logging**: Complete trail of all user and system actions with GDPR compliance
- **Field Encryption**: Fernet encryption for PII and sensitive data
- **Outbox Pattern**: Reliable at-least-once event publishing

### GDPR Compliance

- **Account Deletion**: Self-service right to erasure (Article 17) — anonymizes PII, revokes API keys, invalidates all JWTs
- **Data Export**: Right to data portability (Article 20) — JSON attachment with profile, API keys, and audit activity

### File Storage

- **Object Storage**: MinIO / S3-compatible blob storage for documents, images, and files
- **Deduplication**: SHA-256 content hash dedup, identical files share storage via reference counting
- **Image Processing**: Automatic thumbnail generation and dimension extraction via Pillow
- **Presigned URLs**: Time-limited direct download URLs — file bytes never proxy through the API
- **Configurable Limits**: `STORAGE_MAX_FILE_SIZE` setting, easy to adjust per deployment

### Core Infrastructure

- **FastAPI 0.115+**: Modern async Python web framework
- **SQLModel**: Pydantic + SQLAlchemy hybrid ORM (consistent imports throughout)
- **PostgreSQL**: Production-grade relational database with `pg_trgm` and `unaccent` extensions
- **Compound Indexes**: Performance-optimized compound indexes on `audit_logs`, `api_keys`, and `outbox_events`
- **Redis**: Caching, rate limiting, Celery result backend
- **Celery**: Background task processing with RabbitMQ (AMQPS/TLS) broker
- **RedBeat**: Redis-backed Celery beat scheduler

### Search

- **PostgreSQL Full-Text Search**: `to_tsvector`/`plainto_tsquery` with configurable language
- **Trigram Similarity**: Fuzzy matching via `pg_trgm` with GIN indexes
- **Greek Support**: Greeklish-to-Greek transliteration, unaccent normalization, Greek Hunspell configuration ready
- **`SearchMixin`**: Reusable repository mixin for multi-field search on any SQLModel table
- **Auto-dispatch**: Short queries use trigram, long queries use FTS

### Reliability

- **Idempotency**: `X-Idempotency-Key` header support on mutating endpoints, safe retries without duplicate side effects
- **Circuit Breaker**: Protect external service calls from cascading failures
- **Token Invalidation**: `token_version` claim on all JWTs — password reset, 2FA change, and account deletion immediately block all sessions
- **Resilient Container Startup**: Automated retries on transient Docker Hub/network failures

### Pagination

- **RFC 5988 Link Headers**: `X-Total-Count` and `Link` (first, last, prev, next) on all list endpoints
- **`PaginatedResponse`**: Reusable response wrapper — new list endpoints auto-inherit pagination headers

### Developer Experience

- **uv**: Fast Python package manager (10-100x faster than Poetry)
- **Structured Logging**: JSON logs with correlation IDs
- **Docker Compose**: Local development with all services, auto-generated self-signed TLS certs
- **API Documentation**: Auto-generated OpenAPI/Swagger docs
- **Pre-commit Hooks**: Code quality checks
- **Startup Smoke Tests**: Celery config validation & health-check task execution

### Security

- **TOTP 2FA**: Encrypted secrets at rest, bcrypt-hashed recovery codes, Redis-backed rate limiting and replay prevention
- **Rate Limiting**: Redis-based sliding window limiter per user and per API key
- **Password Hashing**: bcrypt with automatic updates
- **Timing Attack Prevention**: Constant-time password verification with dummy hash fallback
- **CSRF Protection**: State tokens bound to redirect URIs for OAuth flows (prevents open-redirect attacks)
- **CORS Configuration**: Easy frontend integration
- **TLS Everywhere**: RabbitMQ/PostgreSQL connections secured via auto-generated self-signed certificates

### Observability

- **Structured JSON Logging**: structlog with correlation IDs
- **OpenTelemetry Tracing**: Distributed trace support
- **GlitchTip**: Self-hosted error tracking (Sentry SDK compatible)
- **Flower**: Celery worker monitoring dashboard
- **Health Metrics**: Pool stats, cache stats, readiness/liveness probes

### DevOps

- **GitHub Actions CI/CD**: Lint, type check, test, security scan (Trivy)
- **Traefik + Let's Encrypt**: Automatic HTTPS for production
- **Metabase**: BI dashboards and data exploration
- **Mailpit**: Email testing in development
- **PGAdmin4**: PostgreSQL management UI
- **Redis Commander**: Redis management UI

## Quick Start

You need:

- [uv](https://docs.astral.sh/uv/getting-started/installation/)
- [Docker](https://docs.docker.com/engine/install/)

First time only:

```bash
./scripts/setup.sh
```

Every time you want to run or showcase the project:

```bash
./scripts/demo.sh
```

`demo.sh` starts every service (Postgres, Redis, RabbitMQ, Metabase), applies
migrations, seeds demo data, prints the API and Metabase URLs plus the demo
login, then runs the API server in the foreground. `Ctrl+C` stops the API
server, the containers keep running.

## Thesis

The manuscript lives in `thesis/` as LaTeX, built with XeLaTeX + biber.

```bash
# Build once, output at thesis/main.pdf, also copies to documents/<author>-thesis.pdf.
./scripts/export-thesis.sh

# No local TeX install? Build inside the official TeX Live container instead.
./scripts/export-thesis.sh --docker

# Rebuild continuously while editing, from inside thesis/.
cd thesis && make watch
```

`documents/<author>-thesis.pdf`, generated by `export-thesis.sh`, is the
file to hand over. CI (`Thesis CI` in `.github/workflows/thesis.yml`) also
builds and uploads `main.pdf` as a workflow artifact on every push touching
`thesis/`, so a from-scratch build is never required to get a copy.

## Useful Commands

```bash
# Full automated setup including environment variables, containerization, and initial data.
./scripts/setup.sh

# Synchronize with upstream YAP template changes.
./scripts/synchronize.sh

# Start dev server.
uv run fastapi dev app/main.py --host 0.0.0.0 --port 8000

# Start all services.
docker compose up -d

# Run tests.
uv run pytest

# Auto-fix lint issues.
./scripts/lint.sh --fix

# Create migration.
uv run alembic revision --autogenerate -m "Add users table"

# Run migrations.
uv run alembic upgrade head

# Rollback.
uv run alembic downgrade -1

# Start celery worker.
uv run celery -A app.celery_app worker --loglevel=info

# Start celery beat/scheduler.
uv run celery -A app.celery_app beat --loglevel=info
```

## API Documentation

FastAPI auto-generates interactive documentation with "Try it out":

- **Swagger UI** ([http://localhost:8000/try](http://localhost:8000/try)): Interactive "Try it out" for every endpoint.
- **ReDoc** ([http://localhost:8000/documentation](http://localhost:8000/documentation)): Clean reference documentation

Operation IDs use `<tag>-<route_name>` format for clean client code generation.
All request/response schemas are fully validated and documented. Paginated list endpoints return `X-Total-Count` and `Link` (RFC 5988) headers.

## Analytics Endpoints

Once data is ingested (see below), these routes turn it into insight. Full request/response shapes are in Swagger.

| Prefix | What it answers |
| --- | --- |
| `/api/v1/analytics` | Descriptive breakdowns: sales by product, region, time, price band, characteristic. |
| `/api/v1/business-metrics` | GMV, repeat-purchase rate, cohort retention, RFM, revenue concentration. |
| `/api/v1/segmentation` | Two-level customer clustering (region/time, then RFM), k chosen by silhouette score. |
| `/api/v1/market-basket` | Frequent itemset mining (Apriori/FP-Growth) and association rules. Mining runs are queued to a background worker; `GET .../rules` reads the stored results. |
| `/api/v1/forecasting` | Holt-Winters exponential-smoothing revenue forecasts, evaluated against a naive baseline out of sample. |
| `/api/v1/growth-accounting` | Revenue decomposed into new/resurrected/retained/expansion/contraction/churned flows. |
| `/api/v1/profitability` | LTV, CAC, LTV:CAC and unit-economics sensitivity grids, computed from explicitly stated assumptions, never presented as measurements. |

## Bring Your Own Data

The platform is not tied to the Online Retail II dataset used in the thesis. Everything downstream (analytics, clustering, forecasting, dashboards) runs off one canonical transaction-line shape: `order_number`, `ordered_at`, `stock_code`, `quantity`, `unit_price`, plus optional `description`/`customer_identifier`/`region_name`/`is_cancellation`.

Three ways to deliver it, no code required for the first two:

1. **Push a batch** — `POST /api/v1/ingestion/transactions` with up to 5000 lines. Redelivering the same batch is safe, already-imported transactions are skipped, not duplicated.
2. **Point at a database** — describe which columns hold which canonical field via `SQLSourceConfiguration`, and a background task streams rows in from any database SQLAlchemy can reach. No per-merchant code.
3. **Write a file adapter** — only needed for a file layout that doesn't fit the first two; implement `DataSourceAdapter` the way `app/ingestion/online_retail.py` does for the reference dataset.

Full field-by-field rules (what's required, what gets rejected and why, exact request/response examples) are in [`documents/ingestion-contract.md`](documents/ingestion-contract.md). Every deployment is tenant-scoped, so one running instance can hold more than one merchant's data without them ever seeing each other's numbers.

## Business Intelligence Dashboards

Metabase ships as part of the stack (`docker compose up -d` starts it, `demo.sh` prints its URL) with 12 pre-built SQL cards under [`metabase/queries/`](metabase/queries/) that mirror the analytics endpoints one-to-one, so the dashboard and the API never disagree about a number. Metabase connects through a dedicated read-only database user (`metabase_read_only`, generated by `setup.sh` into `.env`), so a dashboard can never write to the data it's exploring. Setup steps and card-by-card notes are in [`metabase/README.md`](metabase/README.md).

## Relationship to `yap`

This project is generated from [`yap`](https://github.com/xrhstosmour/yap), a Copier template, and stays in sync with it via `./scripts/synchronize.sh`. Everything generic — authentication, multi-tenancy, GDPR tooling, file storage, rate limiting, the Celery/RabbitMQ setup, the Docker Compose services (PostgreSQL, Redis, Metabase, and friends) — comes from `yap`. `app/ingestion/` and `app/analysis/` (and everything built on top of them: the analytics endpoints, the thesis, the notebooks) are specific to this project and never flow upstream. A generic bug found here gets fixed in `yap` first, then pulled back in with a sync, so the fix benefits every other project generated from the same template.

## License

MIT License - see [LICENSE](LICENSE) file.
