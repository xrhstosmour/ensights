"""Seed the showcase database with synthetic transactions.

`app/initial_data.py` creates the tenant, the superuser and the Metabase
read-only role, which is everything the platform needs to start but nothing it
needs to say anything. This script fills in the commerce facts, so a first run
of `scripts/demo.sh` lands on a system where every endpoint and every Metabase
card returns real numbers instead of an empty list.

The data is synthetic and its figures mean nothing on their own. Reproducing
the manuscript's numbers still requires importing the real Online Retail II
dataset, which the README explains.

Run through `uv run --env-file .env python scripts/seed_demo.py`, or let
`scripts/demo.sh` call it.
"""

from __future__ import annotations

import asyncio
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import func  # noqa: E402
from sqlmodel import select  # noqa: E402

from app.core import SYSTEM_TENANT_ID  # noqa: E402
from app.core.tenant import set_current_tenant_id  # noqa: E402
from app.database import async_session_factory  # noqa: E402
from app.ingestion.demo import DemoDataAdapter  # noqa: E402
from app.models.order import Order  # noqa: E402
from app.services.ingestion_service import IngestionService  # noqa: E402
from app.services.market_basket_service import MarketBasketService  # noqa: E402

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Low enough that the small synthetic catalogue still produces rules. The
# API's own default is the same, so a card and the endpoint agree.
MINIMUM_SUPPORT = 0.01
MINIMUM_CONFIDENCE = 0.3


async def seed() -> None:
    """Import the demo transactions and mine their baskets.

    Skips the import when orders already exist, so re-running `demo.sh` is
    cheap and never doubles the data. Mining always runs, because the rules
    are derived rather than ingested and a schema change can leave them stale.
    """
    # Ingestion and every analytical read are tenant-scoped, and
    # `AnalyticsRepository._scope` raises rather than run unfiltered, so the
    # context has to be set before either. The system tenant is the one
    # `app/initial_data.py` puts the superuser in.
    set_current_tenant_id(SYSTEM_TENANT_ID)

    async with async_session_factory() as session:
        existing = await session.execute(
            select(func.count()).select_from(Order).where(Order.deleted_at.is_(None))  # type: ignore[attr-defined]
        )
        order_count = existing.scalar_one()

        if order_count:
            logger.info(
                "Demo data already present, %s orders, skipping import", order_count
            )
        else:
            adapter = DemoDataAdapter()
            logger.info("Importing demo transactions from %s...", adapter.source_name)
            summary = await IngestionService(session).import_from(adapter)
            logger.info(
                "Imported %s orders, %s order lines, %s returns",
                summary.orders_created,
                summary.order_items_created,
                summary.returns_created,
            )

    async with async_session_factory() as session:
        # Mining normally runs as a Celery task, and `demo.sh` starts no
        # worker. Calling the service directly is what keeps the association
        # rules card and `/market-basket/rules` from being empty.
        logger.info("Mining market baskets...")
        _run_identifier, result = await MarketBasketService(session).run(
            algorithm="fpgrowth",
            minimum_support=MINIMUM_SUPPORT,
            minimum_confidence=MINIMUM_CONFIDENCE,
        )
        logger.info(
            "Mined %s baskets into %s itemsets and %s rules",
            result.basket_count,
            len(result.itemsets),
            len(result.rules),
        )


def main() -> None:
    """Entry point."""
    asyncio.run(seed())
    logger.info("Demo data ready")


if __name__ == "__main__":
    main()
