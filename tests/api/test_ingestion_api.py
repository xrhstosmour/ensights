"""Tests for the transaction ingestion API endpoint."""

from __future__ import annotations

from collections.abc import Generator
from typing import Any
from typing import Literal

import pytest
from httpx import ASGITransport
from httpx import AsyncClient

from app.main import app
from app.models.user import User
from app.models.user import UserRole

ENDPOINT = "/api/v1/ingestion/transactions"


def line(**overrides: Any) -> dict[str, Any]:  # noqa: ANN401
    """Build one canonical transaction line for a request body.

    Args:
        **overrides: Fields to override on the default line.

    Returns:
        The line as it travels over the wire.
    """
    payload: dict[str, Any] = {
        "order_number": "SO-1",
        "ordered_at": "2024-03-01T10:00:00",
        "stock_code": "TEA-01",
        "quantity": 2,
        "unit_price": "4.50",
        "description": "Green tea",
        "customer_identifier": "buyer-1",
        "region_name": "Greece",
    }
    payload.update(overrides)
    return payload


@pytest.fixture
def anyio_backend() -> Literal["asyncio"]:
    """Provide the asyncio backend for anyio-marked tests.

    Returns:
        The backend name.
    """
    return "asyncio"


@pytest.fixture
async def client() -> Generator[AsyncClient, Any]:
    """Provide an HTTP client bound to the application.

    Yields:
        The client to issue requests with.
    """
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


async def authenticate(session: Any, email: str) -> dict[str, str]:  # noqa: ANN401
    """Create a user and return the authorization header for it.

    Args:
        session: Async database session fixture.
        email: Address to register the user under.

    Returns:
        The authorization header to send with requests.
    """
    from app.services.auth_service import AuthService

    service = AuthService(session)
    user = User(
        email=email,
        hashed_password="hash",
        role=UserRole.USER,
        is_active=True,
    )
    session.add(user)
    await session.commit()
    tokens = service.create_tokens(user)
    return {"Authorization": f"Bearer {tokens.access_token}"}


@pytest.mark.anyio
async def test_import_requires_authentication(client: AsyncClient) -> None:
    """An anonymous caller must not be able to write transactions.

    Args:
        client: HTTP client bound to the application.

    Returns:
        None.
    """
    response = await client.post(ENDPOINT, json={"records": [line()]})

    assert response.status_code == 401


@pytest.mark.anyio
@pytest.mark.usefixtures("override_get_async_session")
async def test_import_creates_orders_and_reports_counters(
    client: AsyncClient,
    session: Any,  # noqa: ANN401
) -> None:
    """A posted batch should be imported and counted back to the caller.

    Args:
        client: HTTP client bound to the application.
        session: Async database session fixture.

    Returns:
        None.
    """
    headers = await authenticate(session, "ingest-counters@example.com")

    response = await client.post(
        ENDPOINT,
        json={
            "source_name": "shopify-export",
            "records": [line(), line(stock_code="MUG-02", unit_price="12.00")],
        },
        headers=headers,
    )

    assert response.status_code == 201
    body = response.json()
    assert body["source_name"] == "shopify-export"
    assert body["records_received"] == 2
    assert body["records_accepted"] == 2
    assert body["orders_created"] == 1
    assert body["order_items_created"] == 2
    assert body["customers_created"] == 1
    assert body["regions_created"] == 1
    assert body["rejected"] == []


@pytest.mark.anyio
@pytest.mark.usefixtures("override_get_async_session")
async def test_import_reports_rejected_lines_individually(
    client: AsyncClient,
    session: Any,  # noqa: ANN401
) -> None:
    """Lines that fail the shared rules must come back named, not just counted.

    Args:
        client: HTTP client bound to the application.
        session: Async database session fixture.

    Returns:
        None.
    """
    headers = await authenticate(session, "ingest-rejected@example.com")

    response = await client.post(
        ENDPOINT,
        json={
            "records": [
                line(order_number="SO-10"),
                line(order_number="SO-11", unit_price="0.00"),
                line(order_number="SO-12", quantity=0),
                line(order_number="SO-13", stock_code="POSTAGE"),
            ],
            "non_product_codes": ["postage"],
        },
        headers=headers,
    )

    assert response.status_code == 201
    body = response.json()
    assert body["records_received"] == 4
    assert body["records_accepted"] == 1
    assert [(entry["order_number"], entry["reason"]) for entry in body["rejected"]] == [
        ("SO-11", "non_positive_price"),
        ("SO-12", "zero_quantity"),
        ("SO-13", "non_product_code"),
    ]


@pytest.mark.anyio
@pytest.mark.usefixtures("override_get_async_session")
async def test_reposting_the_same_batch_does_not_duplicate(
    client: AsyncClient,
    session: Any,  # noqa: ANN401
) -> None:
    """A retried delivery must not double the merchant's revenue.

    Args:
        client: HTTP client bound to the application.
        session: Async database session fixture.

    Returns:
        None.
    """
    headers = await authenticate(session, "ingest-repost@example.com")
    payload = {"records": [line(order_number="SO-20")]}

    first = await client.post(ENDPOINT, json=payload, headers=headers)
    second = await client.post(ENDPOINT, json=payload, headers=headers)

    assert first.json()["orders_created"] == 1
    assert second.json()["orders_created"] == 0
    assert second.json()["transactions_skipped"] == 1


@pytest.mark.anyio
@pytest.mark.usefixtures("override_get_async_session")
async def test_splitting_one_transaction_across_batches_drops_the_remainder(
    client: AsyncClient,
    session: Any,  # noqa: ANN401
) -> None:
    """Skipping is per transaction, which the contract documents as a rule.

    Whole transactions must be sent together: the second half of a split
    transaction is skipped, because the transaction already exists by then.
    This test exists to keep the documented behaviour and the implemented one
    from drifting apart.

    Args:
        client: HTTP client bound to the application.
        session: Async database session fixture.

    Returns:
        None.
    """
    headers = await authenticate(session, "ingest-split@example.com")

    first = await client.post(
        ENDPOINT,
        json={"records": [line(order_number="SO-40")]},
        headers=headers,
    )
    second = await client.post(
        ENDPOINT,
        json={"records": [line(order_number="SO-40", stock_code="MUG-02")]},
        headers=headers,
    )

    assert first.json()["order_items_created"] == 1
    assert second.json()["order_items_created"] == 0
    assert second.json()["transactions_skipped"] == 1


@pytest.mark.anyio
@pytest.mark.usefixtures("override_get_async_session")
async def test_cancellation_flag_creates_a_return(
    client: AsyncClient,
    session: Any,  # noqa: ANN401
) -> None:
    """A flagged reversal must land as a return rather than a sale.

    Args:
        client: HTTP client bound to the application.
        session: Async database session fixture.

    Returns:
        None.
    """
    headers = await authenticate(session, "ingest-return@example.com")

    response = await client.post(
        ENDPOINT,
        json={
            "records": [
                line(
                    order_number="SO-30",
                    quantity=-2,
                    is_cancellation=True,
                )
            ]
        },
        headers=headers,
    )

    body = response.json()
    assert body["returns_created"] == 1
    assert body["order_items_created"] == 0


@pytest.mark.anyio
@pytest.mark.usefixtures("override_get_async_session")
async def test_empty_batch_is_rejected(
    client: AsyncClient,
    session: Any,  # noqa: ANN401
) -> None:
    """An empty batch is a caller mistake, not a no-op import.

    Args:
        client: HTTP client bound to the application.
        session: Async database session fixture.

    Returns:
        None.
    """
    headers = await authenticate(session, "ingest-empty@example.com")

    response = await client.post(ENDPOINT, json={"records": []}, headers=headers)

    assert response.status_code == 422
