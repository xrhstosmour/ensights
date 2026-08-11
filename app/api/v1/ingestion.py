"""Data ingestion API routes.

The push half of the ingestion contract: a merchant sends transaction lines in
the canonical form documented in `documents/ingestion-contract.md` and the
system imports them without knowing anything about the shop they came from.

The pull half, reading a merchant's own database, is configuration rather than
a request, and is dispatched through
`app.tasks.ingestion.import_sql_source_task`.
"""

from __future__ import annotations

from fastapi import APIRouter
from fastapi import status

from app.core.logging import get_logger
from app.dependencies import CurrentUser
from app.dependencies import SessionDependency
from app.schemas.ingestion import ImportResult
from app.schemas.ingestion import RejectedLine
from app.schemas.ingestion import TransactionBatchIn
from app.services.ingestion_service import IngestionService

router = APIRouter(prefix="/ingestion", tags=["Ingestion"])
logger = get_logger("api.ingestion")


@router.post(
    "/transactions",
    response_model=ImportResult,
    status_code=status.HTTP_201_CREATED,
    summary="Import a batch of transaction lines",
    description=(
        "Imports transaction lines already normalised to the canonical schema. "
        "Re-sending a batch is safe: transactions already present are skipped "
        "whole rather than duplicated."
    ),
)
async def import_transactions(
    batch: TransactionBatchIn,
    session: SessionDependency,
    _current_user: CurrentUser,
) -> ImportResult:
    """Import a batch of canonical transaction lines.

    Args:
        batch: The submitted lines and their provenance.
        session: Async database session.
        _current_user: Authenticated caller, tenant-scoped.

    Returns:
        What the run created, alongside the lines it turned away.
    """
    service = IngestionService(session)
    result = await service.import_batch(
        records=[line.to_canonical() for line in batch.records],
        source_name=batch.source_name,
        non_product_codes=frozenset(
            code.strip().upper() for code in batch.non_product_codes if code.strip()
        ),
    )

    summary = result.summary
    return ImportResult(
        source_name=batch.source_name,
        records_received=result.records_received,
        records_accepted=result.records_accepted,
        orders_created=summary.orders_created,
        order_items_created=summary.order_items_created,
        returns_created=summary.returns_created,
        transactions_skipped=summary.transactions_skipped,
        customers_created=summary.customers_created,
        products_created=summary.products_created,
        regions_created=summary.regions_created,
        rejected=[
            RejectedLine(
                index=entry.index,
                order_number=entry.order_number,
                reason=entry.reason,
            )
            for entry in result.rejected
        ],
    )
