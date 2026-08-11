"""Adapter over transaction lines that are already in canonical form.

This is the path a merchant takes when they push data instead of the system
pulling it: the caller has already mapped their own schema onto the canonical
one, so nothing is left to parse. It exists as an adapter rather than a
shortcut into the ingestion service so that a posted batch travels the same
code path as a file or a database, and cannot drift from it.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from app.core.logging import get_logger
from app.ingestion.base import DataSourceAdapter

if TYPE_CHECKING:
    from collections.abc import Iterable
    from collections.abc import Iterator

    from app.ingestion.base import CanonicalRecord

logger = get_logger("ingestion.records")


class RecordSequenceAdapter(DataSourceAdapter):
    """Yields canonical records supplied directly by the caller.

    Attributes:
        records: The lines to import
        name: Provenance label reported in logs
    """

    def __init__(
        self,
        records: Iterable[CanonicalRecord],
        name: str = "posted-batch",
    ) -> None:
        """Initialise the adapter.

        Args:
            records: Lines already normalised to the canonical schema.
            name: Where the batch came from, for logs and provenance.
        """
        self.records = records
        self.name = name

    def fetch(self) -> Iterator[CanonicalRecord]:
        """Yield the supplied lines unchanged.

        Yields:
            One `CanonicalRecord` per supplied line.
        """
        count = 0
        for record in self.records:
            count += 1
            yield record

        logger.info("record_sequence_fetch_complete", source=self.name, yielded=count)

    @property
    def source_name(self) -> str:
        """Provenance label for this batch.

        Returns:
            The name given at construction.
        """
        return self.name
