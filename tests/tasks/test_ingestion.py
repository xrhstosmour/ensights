"""Tests for the ingestion Celery tasks."""

from __future__ import annotations

import sys
from contextlib import asynccontextmanager
from typing import Any
from unittest.mock import AsyncMock
from unittest.mock import MagicMock
from unittest.mock import patch

import pytest

# See tests/tasks/test_cleanup.py for why this stub eviction is needed.
if isinstance(sys.modules.get("app.tasks.ingestion"), MagicMock):
    del sys.modules["app.tasks.ingestion"]

from app.tasks.ingestion import import_online_retail_task  # noqa: E402
from app.tasks.ingestion import import_sql_source_task  # noqa: E402


@pytest.fixture
def mock_session_factory(monkeypatch: pytest.MonkeyPatch) -> AsyncMock:
    mock_session = AsyncMock()

    @asynccontextmanager
    async def _factory() -> Any:
        yield mock_session

    monkeypatch.setattr("app.database.celery_session_factory", _factory)
    return mock_session


class TestImportOnlineRetailTask:
    """Tests for import_online_retail_task()."""

    def test_retries_on_failure(self, mock_session_factory: AsyncMock) -> None:
        """A transient failure while importing should trigger a retry
        instead of failing the task outright on the first attempt."""
        with patch(
            "app.services.ingestion_service.IngestionService.import_from",
            new=AsyncMock(side_effect=OSError("connection reset")),
        ):
            result = import_online_retail_task.apply(kwargs={"path": "irrelevant.csv"})

        assert result.failed()


class TestImportSqlSourceTask:
    """Tests for import_sql_source_task()."""

    def test_retries_on_failure(self, mock_session_factory: AsyncMock) -> None:
        """A transient failure while importing should trigger a retry
        instead of failing the task outright on the first attempt."""
        configuration = {
            "url": "postgresql://user:pass@host/db",
            "query": "SELECT 1",
            "columns": {
                "order_number": "order_number",
                "ordered_at": "ordered_at",
                "stock_code": "stock_code",
                "quantity": "quantity",
                "unit_price": "unit_price",
            },
        }

        with patch(
            "app.services.ingestion_service.IngestionService.import_from",
            new=AsyncMock(side_effect=OSError("connection reset")),
        ):
            result = import_sql_source_task.apply(
                kwargs={"configuration": configuration}
            )

        assert result.failed()
