"""Data ingestion: source adapters that feed the canonical schema.

Analytics never read a vendor's schema directly. Every source is wrapped in a
`DataSourceAdapter` that yields `CanonicalRecord` values, so pointing this
system at a different store means writing one adapter rather than touching any
analytical code.
"""

from app.ingestion.base import CanonicalRecord
from app.ingestion.base import DataSourceAdapter
from app.ingestion.online_retail import OnlineRetailCSVAdapter

__all__ = [
    "CanonicalRecord",
    "DataSourceAdapter",
    "OnlineRetailCSVAdapter",
]
