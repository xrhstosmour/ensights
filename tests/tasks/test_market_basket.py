"""Tests for the market basket Celery tasks."""

from __future__ import annotations

import sys
from contextlib import asynccontextmanager
from typing import Any
from unittest.mock import AsyncMock
from unittest.mock import MagicMock
from unittest.mock import patch

import pytest

# See tests/tasks/test_cleanup.py for why this stub eviction is needed.
if isinstance(sys.modules.get("app.tasks.market_basket"), MagicMock):
    del sys.modules["app.tasks.market_basket"]

from app.tasks.market_basket import mine_market_baskets_task  # noqa: E402


@pytest.fixture
def mock_session_factory(monkeypatch: pytest.MonkeyPatch) -> AsyncMock:
    mock_session = AsyncMock()

    @asynccontextmanager
    async def _factory() -> Any:
        yield mock_session

    monkeypatch.setattr("app.database.celery_session_factory", _factory)
    return mock_session


class TestMineMarketBasketsTask:
    """Tests for mine_market_baskets_task()."""

    def test_retries_on_failure(self, mock_session_factory: AsyncMock) -> None:
        """A transient failure while mining should trigger a retry instead
        of failing the task outright on the first attempt."""
        with patch(
            "app.services.market_basket_service.MarketBasketService.run",
            new=AsyncMock(side_effect=OSError("connection reset")),
        ):
            result = mine_market_baskets_task.apply()

        assert result.failed()
