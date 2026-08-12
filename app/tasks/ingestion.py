"""Data import background tasks via Celery.

Importing a full retail export runs to millions of lines, far past any
request's lifetime, so imports are always dispatched to a worker.
"""

from __future__ import annotations

from app.celery_app import celery_app
from app.core.logging import get_logger

logger = get_logger("tasks.ingestion")


@celery_app.task(
    bind=True,
    name="app.tasks.ingestion.import_online_retail",
    max_retries=1,
    default_retry_delay=60,
)
def import_online_retail_task(self, path: str, tenant_id: str | None = None) -> dict:
    """Import an Online Retail II CSV export into the canonical schema.

    Args:
        path: Location of the CSV file to import.
        tenant_id: Tenant to attribute the imported rows to, when scoping the
            import to one store.

    Returns:
        Result dict with the import counters.
    """
    import asyncio
    from uuid import UUID

    from app.core import SYSTEM_TENANT_ID
    from app.core.tenant import set_current_tenant_id
    from app.database import celery_session_factory
    from app.ingestion.online_retail import OnlineRetailCSVAdapter
    from app.services.ingestion_service import IngestionService

    async def _run() -> dict:
        # A caller with no tenant to scope the import to still needs a real
        # tenant context, or every tenant-scoped write/read in the import
        # would have none either. Falls back to the system tenant, the
        # same fallback used elsewhere for tenant-less operations.
        set_current_tenant_id(UUID(tenant_id) if tenant_id else SYSTEM_TENANT_ID)

        async with celery_session_factory() as session:
            service = IngestionService(session)
            summary = await service.import_from(OnlineRetailCSVAdapter(path))

        return {
            "status": "completed",
            "orders_created": summary.orders_created,
            "order_items_created": summary.order_items_created,
            "returns_created": summary.returns_created,
            "transactions_skipped": summary.transactions_skipped,
            "customers_created": summary.customers_created,
            "products_created": summary.products_created,
            "regions_created": summary.regions_created,
        }

    return asyncio.run(_run())


@celery_app.task(
    bind=True,
    name="app.tasks.ingestion.import_sql_source",
    max_retries=1,
    default_retry_delay=60,
)
def import_sql_source_task(
    self, configuration: dict, tenant_id: str | None = None
) -> dict:
    """Import transaction lines straight out of a merchant's own database.

    No adapter is written per merchant: the configuration carries the query and
    the mapping from their column names onto the canonical fields.

    Args:
        configuration: `SQLSourceConfiguration` fields, as a mapping.
        tenant_id: Tenant to attribute the imported rows to, when scoping the
            import to one store.

    Returns:
        Result dict with the import counters.

    Raises:
        ValueError: If the configuration is not a usable source definition,
            for example a mapping missing a required canonical field.
    """
    import asyncio
    from uuid import UUID

    from pydantic import ValidationError

    from app.core import SYSTEM_TENANT_ID
    from app.core.tenant import set_current_tenant_id
    from app.database import celery_session_factory
    from app.ingestion.sql_source import SQLDataSourceAdapter
    from app.ingestion.sql_source import SQLSourceConfiguration
    from app.services.ingestion_service import IngestionService

    try:
        source = SQLSourceConfiguration(**configuration)
    except ValidationError as error:
        message = f"Invalid SQL source configuration: {error}"
        raise ValueError(message) from error

    async def _run() -> dict:
        # See import_online_retail_task() for why this falls back rather
        # than skipping when there is no tenant to scope the import to.
        set_current_tenant_id(UUID(tenant_id) if tenant_id else SYSTEM_TENANT_ID)

        async with celery_session_factory() as session:
            service = IngestionService(session)
            summary = await service.import_from(SQLDataSourceAdapter(source))

        return {
            "status": "completed",
            "orders_created": summary.orders_created,
            "order_items_created": summary.order_items_created,
            "returns_created": summary.returns_created,
            "transactions_skipped": summary.transactions_skipped,
            "customers_created": summary.customers_created,
            "products_created": summary.products_created,
            "regions_created": summary.regions_created,
        }

    return asyncio.run(_run())
