"""Integration tests for `Market Basket` API endpoints."""

from __future__ import annotations

from unittest.mock import MagicMock
from unittest.mock import patch
from uuid import UUID
from uuid import uuid7

import pytest
from httpx import ASGITransport
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import SYSTEM_TENANT_ID
from app.core.security import create_access_token
from app.core.security import generate_password_hash
from app.main import app
from app.models.user import UserRole
from app.services.auth_service import AuthService


def _auth_service(session: AsyncSession) -> AuthService:
    return AuthService(session)


async def _create_superuser(auth_service: AuthService, tenant_id: UUID | None = None):
    return await auth_service.user_repository.create_user(
        email=f"admin-{uuid7()}@ensights.com",
        password_hash=generate_password_hash("password123"),
        tenant_id=tenant_id,
        role=UserRole.SUPERUSER,
    )


@pytest.fixture(name="client")
def client_fixture() -> AsyncClient:
    """Create a test client."""
    transport = ASGITransport(app=app)
    return AsyncClient(transport=transport, base_url="http://test")


class TestStartRun:
    """Tests for POST /api/v1/market-basket/runs."""

    @pytest.mark.usefixtures("override_get_async_session")
    async def test_start_run_passes_caller_tenant_to_task(
        self, client: AsyncClient, session: AsyncSession
    ) -> None:
        """The queued task must carry the superuser's tenant, not run unscoped.

        Without this, the worker mines every tenant's orders together and
        the resulting rules are persisted with no tenant attribution.
        """
        auth_service = _auth_service(session)
        superuser = await _create_superuser(auth_service, tenant_id=SYSTEM_TENANT_ID)
        token = create_access_token(subject=superuser.id)

        mock_task = MagicMock()
        mock_task.id = "task-123"

        with patch(
            "app.tasks.market_basket.mine_market_baskets_task.delay",
            return_value=mock_task,
        ) as mock_delay:
            response = await client.post(
                "/api/v1/market-basket/runs",
                headers={"Authorization": f"Bearer {token}"},
            )

        assert response.status_code == 202
        mock_delay.assert_called_once()
        assert mock_delay.call_args.kwargs["tenant_id"] == str(SYSTEM_TENANT_ID)

    @pytest.mark.usefixtures("override_get_async_session")
    async def test_start_run_requires_superuser(
        self, client: AsyncClient, session: AsyncSession
    ) -> None:
        """A non-superuser must not be able to start a mining run."""
        auth_service = _auth_service(session)
        user = await auth_service.user_repository.create_user(
            email=f"user-{uuid7()}@ensights.com",
            password_hash=generate_password_hash("password123"),
            role=UserRole.USER,
        )
        token = create_access_token(subject=user.id)

        response = await client.post(
            "/api/v1/market-basket/runs",
            headers={"Authorization": f"Bearer {token}"},
        )

        assert response.status_code == 403
