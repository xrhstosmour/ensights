"""Shared parsing and validity rules for every ingestion source.

A source is free to decide how it reads its own rows, but not what counts as a
usable transaction line. Those rules live here so a CSV export, a merchant's
own database and a posted JSON batch are all accepted or rejected on identical
grounds, and so the contract published in
`documents/ingestion-contract.md` has exactly one implementation.
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from decimal import InvalidOperation
from typing import TYPE_CHECKING
from typing import Final

if TYPE_CHECKING:
    from app.ingestion.base import CanonicalRecord

# Timestamp layouts seen in real exports, tried in order before falling back to
# ISO 8601 parsing.
DATE_FORMATS: Final[tuple[str, ...]] = (
    "%Y-%m-%d %H:%M:%S",
    "%Y-%m-%d %H:%M",
    "%d/%m/%Y %H:%M",
    "%m/%d/%Y %H:%M",
    "%d/%m/%Y %H:%M:%S",
    "%m/%d/%Y %H:%M:%S",
    "%Y-%m-%d",
)

# Reasons a parsed line is not usable. They are returned rather than raised:
# one bad line in a million-row export is normal, and the import counts them
# instead of failing.
MISSING_IDENTIFIER: Final = "missing_identifier"
ZERO_QUANTITY: Final = "zero_quantity"
NON_POSITIVE_PRICE: Final = "non_positive_price"
NON_PRODUCT_CODE: Final = "non_product_code"
UNPARSEABLE_DATE: Final = "unparseable_date"
UNPARSEABLE_QUANTITY: Final = "unparseable_quantity"
UNPARSEABLE_PRICE: Final = "unparseable_price"


def parse_datetime(raw: object) -> datetime | None:
    """Parse a source timestamp, trying each known export format.

    Args:
        raw: Timestamp from the source, already a datetime or as text.

    Returns:
        The parsed datetime, or None when no known format matches.
    """
    if isinstance(raw, datetime):
        return raw
    if raw is None:
        return None

    text = str(raw).strip()
    if not text:
        return None

    for date_format in DATE_FORMATS:
        try:
            return datetime.strptime(text, date_format)
        except ValueError:
            continue
    try:
        return datetime.fromisoformat(text)
    except ValueError:
        return None


def parse_decimal(raw: object) -> Decimal | None:
    """Parse a source money value.

    A lone comma is treated as a decimal point when it is followed by one
    or two trailing digits (`"4,50"`, the shape of a European money
    value), and as thousands grouping otherwise (`"1,234"`, `"1,234,567"`).
    A comma alongside a dot is always thousands grouping (`"1,234.56"`).

    Args:
        raw: Amount from the source, as a number or as text.

    Returns:
        The parsed decimal, or None when the value is blank, malformed,
        or not finite (NaN/Infinity).
    """
    if isinstance(raw, Decimal):
        value = raw
    elif raw is None:
        return None
    elif isinstance(raw, int | float):
        value = Decimal(str(raw))
    else:
        text = str(raw).strip()
        if not text:
            return None

        if "," in text and "." in text:
            text = text.replace(",", "")
        elif "," in text:
            head, _, tail = text.rpartition(",")
            if tail.isdigit() and len(tail) in (1, 2) and "," not in head:
                text = f"{head}.{tail}"
            else:
                text = text.replace(",", "")

        try:
            value = Decimal(text)
        except InvalidOperation:
            return None

    return value if value.is_finite() else None


def parse_int(raw: object) -> int | None:
    """Parse a source quantity, tolerating values written as decimals.

    Args:
        raw: Quantity from the source, as a number or as text.

    Returns:
        The parsed integer, or None when the value is blank, malformed,
        or not finite (NaN/Infinity).
    """
    if isinstance(raw, bool):
        return None
    if isinstance(raw, int):
        return raw
    if raw is None:
        return None

    text = str(raw).strip()
    if not text:
        return None
    try:
        value = Decimal(text)
        if not value.is_finite():
            return None
        return int(value)
    except (InvalidOperation, ValueError, OverflowError):
        return None


_TRUTHY_TEXT: Final[frozenset[str]] = frozenset({"1", "true", "yes", "y", "t"})


def parse_bool(raw: object) -> bool:
    """Parse a source flag column (e.g. a cancellation indicator).

    Recognizes common textual representations ("Y"/"N", "true"/"false",
    "1"/"0") in addition to native booleans, instead of Python's generic
    truthiness, which treats any non-empty string, including "N" or
    "false", as True.

    Args:
        raw: Flag value from the source.

    Returns:
        The parsed boolean. Unrecognized text and None are treated as
        False, absence or uncertainty means "not flagged".
    """
    if isinstance(raw, bool):
        return raw
    if raw is None:
        return False
    if isinstance(raw, int | float):
        return bool(raw)

    return str(raw).strip().lower() in _TRUTHY_TEXT


def parse_text(raw: object) -> str | None:
    """Normalise an optional free-text field.

    Args:
        raw: Value from the source.

    Returns:
        The stripped text, or None when it is absent or blank.
    """
    if raw is None:
        return None
    text = str(raw).strip()
    return text or None


def classify_record(
    record: CanonicalRecord,
    non_product_codes: frozenset[str] = frozenset(),
) -> str | None:
    """Decide whether a parsed line can support analysis.

    The rules are shared by every source. A line without identifiers cannot be
    attributed, a zero quantity moves nothing, and a non-positive price is a
    stock adjustment or a bad-debt entry rather than trade, which would distort
    every revenue figure it entered.

    Args:
        record: The parsed transaction line.
        non_product_codes: Stock codes the merchant treats as administrative
            rather than merchandise, for example postage or manual
            adjustments. Empty by default, since the codes differ per source.

    Returns:
        The reason the line is unusable, or None when it is usable.
    """
    if not record.order_number.strip() or not record.stock_code.strip():
        return MISSING_IDENTIFIER

    code = record.stock_code.strip().upper()
    if code in non_product_codes:
        return NON_PRODUCT_CODE

    if record.quantity == 0:
        return ZERO_QUANTITY

    if record.unit_price <= 0:
        return NON_POSITIVE_PRICE

    return None


def count_skip(counter: dict[str, int], reason: str) -> None:
    """Record one skipped line against its reason.

    Args:
        counter: Running tally, mutated in place.
        reason: Why the line was skipped.
    """
    counter[reason] = counter.get(reason, 0) + 1
