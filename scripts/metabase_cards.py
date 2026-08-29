"""Create the Metabase data source, cards and dashboards from `metabase/`.

`metabase/README.md` used to describe this as a manual pass: create the card,
paste the SQL, accept the date filters, add it to a dashboard, twelve times.
That is fine once and miserable after a rebuild, and a hand-made card drifts
from the file it was pasted from with nothing to catch it.

This does the same work through the Metabase API, reading the same
`metabase/queries/*.sql` files, so a fresh Metabase reaches the documented
state in one command. Re-running updates the existing cards in place rather
than making a second copy, which is what makes it safe to run after editing a
query.

The Metabase admin account is the project superuser from `.env`, so there is
no extra credential to remember, and the data source connects as
`metabase_readonly`, which `app/initial_data.py` provisions.

Run through `uv run --env-file .env python scripts/metabase_cards.py`.
"""

from __future__ import annotations

import json
import logging
import os
import re
import sys
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger(__name__)

ROOT = Path(__file__).resolve().parent.parent
QUERIES = ROOT / "metabase" / "queries"

# Card names, and the dashboards they belong to, both from
# `metabase/README.md`. Keyed by the numeric prefix of the query file.
CARD_NAMES = {
    "01": "Top Products",
    "02": "Top Customers",
    "03": "Top Regions",
    "04": "Sales Over Time",
    "05": "Sales By Weekday",
    "06": "Top Returns",
    "07": "Price Bands",
    "08": "GMV And Refunds",
    "09": "Cohort Retention",
    "10": "RFM",
    "11": "Association Rules",
    "12": "Revenue Concentration",
}

# Prefixed because the defence deck screenshots them under these exact names,
# and a screenshot that disagrees with the running system invites the question
# it was meant to answer.
DASHBOARDS = [
    (
        "Ensights: Sales",
        "What sold, where and when.",
        ["01", "03", "04", "05", "07"],
    ),
    (
        "Ensights: Customers",
        "Who bought, whether they came back, and how concentrated the revenue is.",
        ["02", "09", "10", "12"],
    ),
    (
        "Ensights: Merchandising",
        "What came back, what sells together, and the headline value.",
        ["06", "11", "08"],
    ),
]

DATA_SOURCE_NAME = "Ensights"

# A comma for the decimal mark and a dot for thousands, so a figure reads
# `379.437,96` the way the manuscript writes it.
NUMBER_SEPARATORS = ",."

TEMPLATE_TAG_PATTERN = re.compile(r"\{\{(\w+)\}\}")


class MetabaseError(RuntimeError):
    """Raised when Metabase rejects a request."""


class Metabase:
    """A very small Metabase API client, session-authenticated."""

    def __init__(self, base_url: str) -> None:
        self.base_url = base_url.rstrip("/")
        self.session: str | None = None

    def call(
        self,
        path: str,
        payload: Any = None,  # noqa: ANN401
        method: str = "POST",
    ) -> Any:  # noqa: ANN401
        """Send one request and decode the response.

        Args:
            path: API path beginning with a slash.
            payload: Body to send as JSON, or None for no body.
            method: HTTP method.

        Returns:
            The decoded JSON, whose shape varies per endpoint, or None when
            the response has no body.

        Raises:
            MetabaseError: If Metabase answers with an HTTP error.
        """
        headers = {"Content-Type": "application/json"}
        if self.session:
            headers["X-Metabase-Session"] = self.session
        request = urllib.request.Request(
            self.base_url + path,
            data=json.dumps(payload).encode() if payload is not None else None,
            method=method,
            headers=headers,
        )
        try:
            with urllib.request.urlopen(request) as response:
                body = response.read()
                return json.loads(body) if body else None
        except urllib.error.HTTPError as error:
            detail = error.read().decode()[:400]
            raise MetabaseError(f"{method} {path} failed: {error.code} {detail}")

    def authenticate(self, email: str, password: str) -> None:
        """Complete first-run setup if needed, then open a session."""
        properties = self.call("/api/session/properties", method="GET")
        assert isinstance(properties, dict)

        if not properties.get("has-user-setup"):
            logger.info("  Running first-run setup")
            self.call(
                "/api/setup",
                {
                    "token": properties["setup-token"],
                    "user": {
                        "first_name": "Admin",
                        "last_name": "Ensights",
                        "email": email,
                        "password": password,
                        "site_name": "Ensights",
                    },
                    "prefs": {"site_name": "Ensights", "allow_tracking": False},
                },
            )

        result = self.call("/api/session", {"username": email, "password": password})
        assert isinstance(result, dict)
        self.session = result["id"]


def environment(key: str, default: str = "") -> str:
    """Read a variable, preferring the real environment over `.env`.

    `demo.sh` and `uv run --env-file .env` both export these already. Falling
    back to parsing `.env` keeps the script runnable on its own.

    Args:
        key: Variable name.
        default: Value to use when the variable is set nowhere.

    Returns:
        The value, or the default.
    """
    if value := os.environ.get(key):
        return value
    env_file = ROOT / ".env"
    if env_file.is_file():
        for line in env_file.read_text().splitlines():
            if line.startswith(f"{key}="):
                return line.split("=", 1)[1].strip().strip('"')
    return default


def ensure_data_source(client: Metabase) -> int:
    """Create the read-only PostgreSQL connection, or find the existing one.

    Args:
        client: An authenticated client.

    Returns:
        The Metabase database id.
    """
    listing = client.call("/api/database", method="GET")
    existing = listing.get("data") if isinstance(listing, dict) else listing
    for database in existing or []:
        if database["name"] == DATA_SOURCE_NAME:
            logger.info(f"  Data source '{DATA_SOURCE_NAME}' already exists")
            return int(database["id"])

    # The host is the Compose service name, which resolves on the project
    # network regardless of what the container is called.
    created = client.call(
        "/api/database",
        {
            "engine": "postgres",
            "name": DATA_SOURCE_NAME,
            "details": {
                "host": "postgresql",
                "port": int(environment("POSTGRESQL_PORT", "5432")),
                "dbname": environment("POSTGRESQL_DATABASE"),
                "user": "metabase_readonly",
                "password": environment("METABASE_READ_ONLY_PASSWORD"),
                "ssl": False,
                "tunnel-enabled": False,
            },
            "is_full_sync": True,
        },
    )
    assert isinstance(created, dict)
    logger.info(f"  Created data source '{DATA_SOURCE_NAME}'")
    return int(created["id"])


def build_card(key: str, sql: str, database_id: int) -> dict[str, Any]:
    """Build the card payload for one query file.

    Metabase needs a template tag declared for every `{{name}}` in the query,
    including the ones inside `[[ ... ]]` optional clauses, otherwise saving
    the card fails. Declaring them here is what the interface would otherwise
    prompt for.

    Args:
        key: Numeric prefix of the query file.
        sql: Contents of the query file.
        database_id: Metabase id of the data source.

    Returns:
        A payload suitable for POST or PUT on `/api/card`.
    """
    tags = {
        tag: {
            "id": f"{key}-{tag}",
            "name": tag,
            "display-name": tag.capitalize(),
            "type": "date",
            "required": False,
        }
        for tag in sorted(set(TEMPLATE_TAG_PATTERN.findall(sql)))
    }
    return {
        "name": CARD_NAMES[key],
        "dataset_query": {
            "type": "native",
            "native": {"query": sql, "template-tags": tags},
            "database": database_id,
        },
        "display": "table",
        "visualization_settings": {},
    }


def ensure_cards(client: Metabase, database_id: int) -> dict[str, int]:
    """Create or update one card per query file.

    Args:
        client: An authenticated client.
        database_id: Metabase id of the data source.

    Returns:
        Card ids keyed by the numeric prefix of the query file.
    """
    listing = client.call("/api/card", method="GET")
    by_name = {card["name"]: card["id"] for card in listing or []}

    cards: dict[str, int] = {}
    for path in sorted(QUERIES.glob("*.sql")):
        key = path.name[:2]
        if key not in CARD_NAMES:
            logger.info(f"  Skipping {path.name}, no card name recorded for it")
            continue
        payload = build_card(key, path.read_text(), database_id)
        name = CARD_NAMES[key]
        if name in by_name:
            client.call(f"/api/card/{by_name[name]}", payload, method="PUT")
            cards[key] = by_name[name]
            logger.info(f"  Updated  {name}")
        else:
            created = client.call("/api/card", payload)
            assert isinstance(created, dict)
            cards[key] = int(created["id"])
            logger.info(f"  Created  {name}")
    return cards


def ensure_dashboards(client: Metabase, cards: dict[str, int]) -> None:
    """Create the three dashboards and lay their cards out two per row.

    Args:
        client: An authenticated client.
        cards: Card ids keyed by query prefix.
    """
    listing = client.call("/api/dashboard", method="GET")
    rows = listing.get("data") if isinstance(listing, dict) else listing
    by_name = {board["name"]: board["id"] for board in rows or []}

    for name, description, keys in DASHBOARDS:
        if name in by_name:
            dashboard_id = by_name[name]
            logger.info(f"  Dashboard '{name}' already exists, replacing its cards")
        else:
            created = client.call(
                "/api/dashboard", {"name": name, "description": description}
            )
            assert isinstance(created, dict)
            dashboard_id = int(created["id"])
            logger.info(f"  Created dashboard '{name}'")

        missing = [key for key in keys if key not in cards]
        if missing:
            logger.info(f"    Skipping cards with no query file: {', '.join(missing)}")

        client.call(
            f"/api/dashboard/{dashboard_id}",
            {
                "dashcards": [
                    {
                        "id": -(index + 1),
                        "card_id": cards[key],
                        "row": (index // 2) * 8,
                        "col": (index % 2) * 12,
                        "size_x": 12,
                        "size_y": 8,
                        "parameter_mappings": [],
                        "visualization_settings": {},
                    }
                    for index, key in enumerate(k for k in keys if k in cards)
                ]
            },
            method="PUT",
        )


def main() -> None:
    """Entry point."""
    base_url = f"http://localhost:{environment('METABASE_PORT', '3000')}"
    email = environment("FIRST_SUPERUSER_EMAIL")
    password = environment("FIRST_SUPERUSER_PASSWORD")
    if not email or not password:
        sys.exit("FIRST_SUPERUSER_EMAIL and FIRST_SUPERUSER_PASSWORD must be set.")

    client = Metabase(base_url)
    logger.info(f"Configuring Metabase at {base_url}")
    try:
        client.authenticate(email, password)
        database_id = ensure_data_source(client)
        cards = ensure_cards(client, database_id)
        ensure_dashboards(client, cards)
        client.call(
            "/api/setting/custom-formatting",
            {"value": {"type/Number": {"number_separators": NUMBER_SEPARATORS}}},
            method="PUT",
        )
        logger.info(f"  Number separators set to '{NUMBER_SEPARATORS}'")
    except MetabaseError as error:
        sys.exit(f"Metabase configuration failed: {error}")

    logger.info(
        f"Metabase ready with {len(cards)} cards on {len(DASHBOARDS)} dashboards."
    )


if __name__ == "__main__":
    main()
