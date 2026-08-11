"""Persists canonical transaction lines into the e-commerce schema.

The service owns the interpretation that adapters deliberately avoid: what a
negative quantity means, how a cancellation maps onto a return, and how the
flat line stream becomes related entities.
"""

from __future__ import annotations

from dataclasses import dataclass
from dataclasses import field
from typing import TYPE_CHECKING
from uuid import UUID

from app.core.logging import get_logger
from app.core.tenant import get_current_tenant_id
from app.ingestion.normalisation import classify_record
from app.ingestion.records import RecordSequenceAdapter
from app.models.customer import Customer
from app.models.order import Order
from app.models.order_item import OrderItem
from app.models.product import Product
from app.models.product_return import ProductReturn
from app.models.region import Region
from app.repositories.commerce_repository import CustomerRepository
from app.repositories.commerce_repository import OrderItemRepository
from app.repositories.commerce_repository import OrderRepository
from app.repositories.commerce_repository import ProductRepository
from app.repositories.commerce_repository import ProductReturnRepository
from app.repositories.commerce_repository import RegionRepository

if TYPE_CHECKING:
    from collections.abc import Iterable
    from collections.abc import Sequence

    from sqlalchemy.ext.asyncio import AsyncSession

    from app.ingestion.base import CanonicalRecord
    from app.ingestion.base import DataSourceAdapter

logger = get_logger("service.ingestion")

# Transactions are committed in batches rather than all at once. A full retail
# history runs to seven figures of rows: committing once at the end would hold
# every object in the session, and lose the entire run to a single late
# failure.
DEFAULT_BATCH_SIZE = 2000


@dataclass
class ImportSummary:
    """Outcome of one import run.

    Attributes:
        orders_created: Sale transactions inserted
        order_items_created: Sale lines inserted
        returns_created: Return lines inserted
        transactions_skipped: Transactions already present, left untouched
        customers_created: New buyers registered
        products_created: New products registered
        regions_created: New regions registered
    """

    orders_created: int = 0
    order_items_created: int = 0
    returns_created: int = 0
    transactions_skipped: int = 0
    customers_created: int = 0
    products_created: int = 0
    regions_created: int = 0


@dataclass(frozen=True, slots=True)
class RejectedRecord:
    """One submitted line that the shared rules turned away.

    Attributes:
        index: Position of the line in the submitted batch
        order_number: Transaction identifier of the line
        reason: Why the line cannot support analysis
    """

    index: int
    order_number: str
    reason: str


@dataclass
class BatchImportResult:
    """Outcome of importing a batch supplied in canonical form.

    Attributes:
        summary: What the run created and skipped
        records_received: Lines submitted, accepted and rejected together
        rejected: Lines that could not be imported
    """

    summary: ImportSummary
    records_received: int = 0
    rejected: list[RejectedRecord] = field(default_factory=list)

    @property
    def records_accepted(self) -> int:
        """Lines that passed the rules.

        Returns:
            Received lines minus rejected ones.
        """
        return self.records_received - len(self.rejected)


@dataclass
class _Caches:
    """Per-run natural-key caches, so repeated rows cost no queries."""

    regions: dict[str, UUID] = field(default_factory=dict)
    customers: dict[str, UUID] = field(default_factory=dict)
    products: dict[str, UUID] = field(default_factory=dict)


class IngestionService:
    """Imports transaction lines from any adapter into the canonical schema."""

    def __init__(self, session: AsyncSession) -> None:
        """Initialise the service.

        Args:
            session: Async database session.
        """
        self.session = session
        self.tenant_id = get_current_tenant_id()
        self.region_repository = RegionRepository(session)
        self.customer_repository = CustomerRepository(session)
        self.product_repository = ProductRepository(session)
        self.order_repository = OrderRepository(session)
        self.order_item_repository = OrderItemRepository(session)
        self.return_repository = ProductReturnRepository(session)

    async def import_from(
        self,
        adapter: DataSourceAdapter,
        batch_size: int = DEFAULT_BATCH_SIZE,
    ) -> ImportSummary:
        """Import every record the adapter yields.

        Records are grouped by transaction, and a transaction already present
        in the database is skipped whole. Re-running an import is therefore
        safe and adds only what is new.

        Args:
            adapter: Source to read from.
            batch_size: Transactions to accumulate before committing.

        Returns:
            Counts describing what the run created and skipped.
        """
        summary = ImportSummary()
        caches = _Caches()
        pending = 0

        for transaction in _group_by_transaction(adapter.fetch()):
            await self._import_transaction(transaction, caches, summary)
            pending += 1
            if pending >= batch_size:
                await self.session.commit()
                pending = 0
                logger.info(
                    "import_progress",
                    orders_created=summary.orders_created,
                    order_items_created=summary.order_items_created,
                    returns_created=summary.returns_created,
                )

        await self.session.commit()

        logger.info(
            "import_complete",
            source=adapter.source_name,
            orders_created=summary.orders_created,
            order_items_created=summary.order_items_created,
            returns_created=summary.returns_created,
            transactions_skipped=summary.transactions_skipped,
        )
        return summary

    async def import_batch(
        self,
        records: Sequence[CanonicalRecord],
        source_name: str = "posted-batch",
        non_product_codes: frozenset[str] = frozenset(),
    ) -> BatchImportResult:
        """Import lines a caller supplied already in canonical form.

        The lines are held to the same rules as any other source, and the ones
        that fail are reported back per line rather than dropped silently: a
        caller who sends a batch is entitled to know exactly which lines did
        not survive it.

        Args:
            records: Lines to import, in canonical form.
            source_name: Where the batch came from, recorded for provenance.
            non_product_codes: Stock codes to treat as administrative rather
                than merchandise.

        Returns:
            The import counters alongside the rejected lines.
        """
        accepted: list[CanonicalRecord] = []
        rejected: list[RejectedRecord] = []

        for index, record in enumerate(records):
            reason = classify_record(record, non_product_codes)
            if reason is None:
                accepted.append(record)
            else:
                rejected.append(
                    RejectedRecord(
                        index=index, order_number=record.order_number, reason=reason
                    )
                )

        summary = await self.import_from(RecordSequenceAdapter(accepted, source_name))

        logger.info(
            "batch_import_complete",
            source=source_name,
            received=len(records),
            accepted=len(accepted),
            rejected=len(rejected),
        )
        return BatchImportResult(
            summary=summary,
            records_received=len(records),
            rejected=rejected,
        )

    async def _import_transaction(
        self,
        records: list[CanonicalRecord],
        caches: _Caches,
        summary: ImportSummary,
    ) -> None:
        """Import one transaction's lines.

        Args:
            records: Lines sharing an order number.
            caches: Per-run natural-key caches.
            summary: Counters to update in place.
        """
        first = records[0]
        is_return = first.is_cancellation or all(
            record.quantity < 0 for record in records
        )

        existing: object | None
        if is_return:
            existing = await self.return_repository.get_by_return_order_number(
                first.order_number
            )
        else:
            existing = await self.order_repository.get_by_order_number(
                first.order_number
            )

        if existing is not None:
            summary.transactions_skipped += 1
            return

        region_id = await self._resolve_region(first.region_name, caches, summary)
        customer_id = await self._resolve_customer(
            first.customer_identifier, region_id, caches, summary
        )

        if is_return:
            await self._create_returns(records, region_id, customer_id, caches, summary)
        else:
            await self._create_order(records, region_id, customer_id, caches, summary)

        await self.session.flush()

    async def _create_order(
        self,
        records: list[CanonicalRecord],
        region_id: UUID | None,
        customer_id: UUID | None,
        caches: _Caches,
        summary: ImportSummary,
    ) -> None:
        """Create a sale and its lines.

        Args:
            records: Lines of the sale.
            region_id: Resolved region.
            customer_id: Resolved buyer.
            caches: Per-run natural-key caches.
            summary: Counters to update in place.
        """
        first = records[0]
        # Constructed rather than created through the repository: the
        # repository flushes and refreshes on every row, which is two round
        # trips per record and unusable at a million of them. The primary key
        # is generated client-side by uuid7(), so the order's id is available
        # to its lines without a flush.
        order = Order(
            tenant_id=self.tenant_id,
            order_number=first.order_number,
            ordered_at=first.ordered_at,
            customer_id=customer_id,
            region_id=region_id,
            is_cancelled=False,
        )
        self.session.add(order)
        summary.orders_created += 1

        for record in records:
            # A negative line inside an otherwise normal invoice is a
            # correction to that invoice. It is recorded as a return so that
            # revenue and refunds stay separately countable.
            product_id = await self._resolve_product(record, caches, summary)
            if record.quantity < 0:
                self.session.add(
                    ProductReturn(
                        tenant_id=self.tenant_id,
                        product_id=product_id,
                        customer_id=customer_id,
                        region_id=region_id,
                        original_order_id=order.id,
                        return_order_number=record.order_number,
                        quantity=abs(record.quantity),
                        amount=abs(record.line_total),
                        returned_at=record.ordered_at,
                    )
                )
                summary.returns_created += 1
                continue

            self.session.add(
                OrderItem(
                    tenant_id=self.tenant_id,
                    order_id=order.id,
                    product_id=product_id,
                    quantity=record.quantity,
                    unit_price=record.unit_price,
                    line_total=record.line_total,
                )
            )
            summary.order_items_created += 1

    async def _create_returns(
        self,
        records: list[CanonicalRecord],
        region_id: UUID | None,
        customer_id: UUID | None,
        caches: _Caches,
        summary: ImportSummary,
    ) -> None:
        """Create the return rows for a cancellation transaction.

        Args:
            records: Lines of the cancellation.
            region_id: Resolved region.
            customer_id: Resolved buyer.
            caches: Per-run natural-key caches.
            summary: Counters to update in place.
        """
        for record in records:
            product_id = await self._resolve_product(record, caches, summary)
            self.session.add(
                ProductReturn(
                    tenant_id=self.tenant_id,
                    product_id=product_id,
                    customer_id=customer_id,
                    region_id=region_id,
                    # The dataset does not reliably link a cancellation back to
                    # the sale it reverses, so this stays unset.
                    original_order_id=None,
                    return_order_number=record.order_number,
                    quantity=abs(record.quantity),
                    amount=abs(record.line_total),
                    returned_at=record.ordered_at,
                )
            )
            summary.returns_created += 1

    async def _resolve_region(
        self,
        name: str | None,
        caches: _Caches,
        summary: ImportSummary,
    ) -> UUID | None:
        """Return the region's id, creating it on first sight.

        Args:
            name: Region name from the source.
            caches: Per-run natural-key caches.
            summary: Counters to update in place.

        Returns:
            The region's identifier, or None when the source has no region.
        """
        if not name:
            return None
        if name in caches.regions:
            return caches.regions[name]

        region = await self.region_repository.get_by_name(name)
        if region is None:
            region = Region(tenant_id=self.tenant_id, name=name)
            self.session.add(region)
            await self.session.flush()
            summary.regions_created += 1

        caches.regions[name] = region.id
        return region.id

    async def _resolve_customer(
        self,
        identifier: str | None,
        region_id: UUID | None,
        caches: _Caches,
        summary: ImportSummary,
    ) -> UUID | None:
        """Return the buyer's id, creating them on first sight.

        Args:
            identifier: Buyer identifier from the source.
            region_id: Region to associate a newly created buyer with.
            caches: Per-run natural-key caches.
            summary: Counters to update in place.

        Returns:
            The buyer's identifier, or None for an anonymous sale.
        """
        if not identifier:
            return None
        if identifier in caches.customers:
            return caches.customers[identifier]

        customer = await self.customer_repository.get_by_external_identifier(identifier)
        if customer is None:
            customer = Customer(
                tenant_id=self.tenant_id,
                external_identifier=identifier,
                region_id=region_id,
            )
            self.session.add(customer)
            await self.session.flush()
            summary.customers_created += 1

        caches.customers[identifier] = customer.id
        return customer.id

    async def _resolve_product(
        self,
        record: CanonicalRecord,
        caches: _Caches,
        summary: ImportSummary,
    ) -> UUID:
        """Return the product's id, creating it on first sight.

        Args:
            record: Line the product was seen on.
            caches: Per-run natural-key caches.
            summary: Counters to update in place.

        Returns:
            The product's identifier.
        """
        if record.stock_code in caches.products:
            return caches.products[record.stock_code]

        product = await self.product_repository.get_by_stock_code(record.stock_code)
        if product is None:
            product = Product(
                tenant_id=self.tenant_id,
                stock_code=record.stock_code,
                description=record.description,
                last_unit_price=record.unit_price,
            )
            self.session.add(product)
            await self.session.flush()
            summary.products_created += 1

        caches.products[record.stock_code] = product.id
        return product.id


def _group_by_transaction(
    records: Iterable[CanonicalRecord],
) -> Iterable[list[CanonicalRecord]]:
    """Group a line stream into transactions.

    Exports of this shape list a transaction's lines consecutively, so grouping
    on runs of equal order numbers keeps memory flat regardless of file size.
    A transaction whose lines are split across the file is imported as two
    groups, and the second is skipped as already present.

    Args:
        records: Line stream from an adapter.

    Yields:
        Lists of lines sharing an order number.
    """
    current_number: str | None = None
    current: list[CanonicalRecord] = []

    for record in records:
        if record.order_number != current_number:
            if current:
                yield current
            current_number = record.order_number
            current = []
        current.append(record)

    if current:
        yield current
