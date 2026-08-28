"""Synthetic transaction source for the showcase.

`scripts/demo.sh` needs a database that every endpoint and every Metabase card
has something to say about, on a machine with no dataset and possibly no
network. The Online Retail II import stays the way to reproduce the figures in
the manuscript; this adapter exists only so a first run is not a tour of empty
responses.

The stream is deliberately shaped rather than uniformly random, because the
analyses each need a different property to be present at all:

- Twenty-four months of history, so `app/analysis/forecasting` has enough
  points to fit and to score against its naive baseline.
- Customers that come back in later months, so cohort retention, RFM and
  growth accounting have retained, expanding, contracting and churned flows
  rather than a wall of one-time buyers.
- Product pairs that genuinely co-occur, so frequent itemset mining finds
  rules with lift above 1 instead of only reflecting popularity.
- Prices covering every band in `PRICE_BANDS`, and descriptions covering every
  keyword group in `PRODUCT_CHARACTERISTICS`, so neither breakdown collapses
  into one bucket.
- Returns, as separate reversing transactions, so refunds are not zero.

Everything is drawn from a seeded `random.Random`, so the same seed produces
the same database. The numbers are invented and mean nothing on their own.
"""

from __future__ import annotations

import random
from datetime import UTC
from datetime import datetime
from datetime import timedelta
from decimal import Decimal
from typing import TYPE_CHECKING

from app.core.logging import get_logger
from app.ingestion.base import CanonicalRecord
from app.ingestion.base import DataSourceAdapter

if TYPE_CHECKING:
    from collections.abc import Iterator

logger = get_logger("ingestion.demo")

# Seed chosen once and pinned, so a reviewer re-running the demo sees the same
# figures a screenshot was taken from.
DEFAULT_SEED = 20260828

DEFAULT_MONTHS = 24
DEFAULT_CUSTOMERS = 300

# Product catalogue. Each entry is a stock code, a description and a unit
# price. The descriptions are written to hit every keyword group in
# `PRODUCT_CHARACTERISTICS`, and the prices to fill every band in
# `PRICE_BANDS`, including the open-ended top one.
CATALOGUE: tuple[tuple[str, str, str], ...] = (
    # 0-1.
    ("DEM001", "PAPER PARTY NAPKIN PACK", "0.42"),
    ("DEM002", "SMALL SEED PACKET WILDFLOWER", "0.65"),
    ("DEM003", "PLAIN PENCIL SET OF THREE", "0.85"),
    ("DEM004", "GIFT WRAP SHEET PLAIN KRAFT", "0.95"),
    # 1-5.
    ("DEM005", "WHITE HANGING HEART T-LIGHT HOLDER", "2.55"),
    ("DEM006", "VINTAGE ENAMEL TEA MUG", "3.25"),
    ("DEM007", "RETRO BAKING SPOON WOODEN", "1.45"),
    ("DEM008", "CHRISTMAS TREE DECORATION STAR", "1.95"),
    ("DEM009", "ADVENT CALENDAR PAPER CARD", "4.25"),
    ("DEM010", "JUTE LUNCH BOX BAG SMALL", "2.75"),
    ("DEM011", "SCENTED CANDLE LAVENDER", "3.95"),
    ("DEM012", "NOTEBOOK RECYCLED PAPER A5", "1.75"),
    ("DEM013", "CERAMIC JAM JAR WITH LID", "4.95"),
    ("DEM014", "WOODEN PUZZLE FARM ANIMALS", "4.50"),
    ("DEM015", "GARDEN PLANT LABEL SET", "2.25"),
    ("DEM016", "SANTA ORNAMENT FELT", "1.65"),
    # 5-10.
    ("DEM017", "ANTIQUE GLASS LANTERN SMALL", "7.95"),
    ("DEM018", "CAKE STAND CERAMIC WHITE", "8.50"),
    ("DEM019", "CANVAS SHOPPER BAG PRINTED", "5.95"),
    ("DEM020", "REINDEER GARLAND FELT", "6.25"),
    ("DEM021", "TOY WOODEN TRAIN CARRIAGE", "9.75"),
    ("DEM022", "FLOWER SEED GROWING KIT", "6.95"),
    ("DEM023", "STONEWARE BOWL SPECKLED", "7.25"),
    ("DEM024", "DESK LAMP FOLDING METAL", "9.95"),
    # 10-50.
    ("DEM025", "VINTAGE SATCHEL LEATHER LOOK", "34.50"),
    ("DEM026", "KITCHEN BAKING SET SIX PIECE", "18.95"),
    ("DEM027", "CHRISTMAS LIGHT STRING WARM WHITE", "22.50"),
    ("DEM028", "GARDEN PLANTER LARGE ZINC", "27.95"),
    ("DEM029", "DOLL PLAYHOUSE WOODEN", "45.00"),
    ("DEM030", "RETRO WALL CLOCK METAL", "29.95"),
    ("DEM031", "TEA SET BONE CHINA FOUR CUP", "38.50"),
    ("DEM032", "HANGING DECORATION MOBILE GLASS", "12.75"),
    ("DEM033", "ANTIQUE STYLE CANDLE LAMP", "16.95"),
    ("DEM034", "BOARD GAME FAMILY EDITION", "24.95"),
    # 50+.
    ("DEM035", "VINTAGE ARMCHAIR THROW WOOL", "89.00"),
    ("DEM036", "GARDEN BENCH FOLDING TEAK", "175.00"),
    ("DEM037", "CHRISTMAS TREE ARTIFICIAL SIX FOOT", "120.00"),
    ("DEM038", "KITCHEN ISLAND TROLLEY OAK", "245.00"),
    ("DEM039", "DOLL HOUSE VICTORIAN LARGE", "95.00"),
    ("DEM040", "ANTIQUE MIRROR GILT FRAME", "310.00"),
)

# Regions, weighted so one dominates. A flat distribution makes the region
# clustering in `app/analysis/clustering` meaningless, since every country
# would look alike.
REGIONS: tuple[tuple[str, int], ...] = (
    ("United Kingdom", 55),
    ("Germany", 9),
    ("France", 8),
    ("Netherlands", 6),
    ("Ireland", 5),
    ("Spain", 4),
    ("Belgium", 4),
    ("Switzerland", 3),
    ("Portugal", 3),
    ("Australia", 3),
)

# Pairs that are bought together far more often than chance. Without these the
# mined rules only rediscover which products are popular, and every lift sits
# at roughly 1.
AFFINITY_PAIRS: tuple[tuple[str, str], ...] = (
    ("DEM005", "DEM011"),
    ("DEM006", "DEM007"),
    ("DEM008", "DEM016"),
    ("DEM009", "DEM020"),
    ("DEM017", "DEM033"),
    ("DEM018", "DEM026"),
    ("DEM019", "DEM010"),
    ("DEM021", "DEM014"),
    ("DEM022", "DEM015"),
    ("DEM031", "DEM023"),
)

# Share of transactions that reverse an earlier sale.
RETURN_RATE = 0.04

# Share of sales with no customer identifier. Real exports carry a large
# anonymous tail, and the customer-level analyses have to cope with it.
ANONYMOUS_RATE = 0.15


class DemoDataAdapter(DataSourceAdapter):
    """Generates a deterministic synthetic transaction stream.

    Attributes:
        seed: Value the internal generator is seeded with
        months: Months of history to produce, ending at `end`
        customers: Size of the customer pool
        end: Exclusive upper bound of the generated history
    """

    def __init__(
        self,
        seed: int = DEFAULT_SEED,
        months: int = DEFAULT_MONTHS,
        customers: int = DEFAULT_CUSTOMERS,
        end: datetime | None = None,
    ) -> None:
        """Initialise the adapter.

        Args:
            seed: Value the internal generator is seeded with, so runs repeat.
            months: Months of history to produce.
            customers: Size of the customer pool.
            end: Exclusive upper bound of the history, defaults to the start
                of the current month so the last generated month is complete.
                A partial final month reads as a collapse to the forecaster,
                which is exactly the artefact chapter 7 has to exclude.
        """
        self.seed = seed
        self.months = months
        self.customers = customers
        self.end = end or _start_of_current_month()

    @property
    def source_name(self) -> str:
        """Name recorded against the import.

        Returns:
            A name that identifies the data as synthetic wherever it is
            logged, so it is never mistaken for the real dataset.
        """
        return f"demo-synthetic-seed-{self.seed}"

    def fetch(self) -> Iterator[CanonicalRecord]:
        """Yield the generated transaction lines.

        Sales are emitted month by month, and a return is emitted directly
        after the sale it reverses, so the ingestion service sees the sale
        first and the two group into separate transactions.

        Yields:
            One `CanonicalRecord` per generated line.
        """
        generator = random.Random(self.seed)
        catalogue = {
            code: (description, Decimal(price))
            for code, description, price in CATALOGUE
        }
        codes = list(catalogue)
        affinity = _affinity_map()

        # A customer's index decides when they first appear, so the pool fills
        # up over time and the cohort grid is triangular rather than square.
        customer_identifiers = [f"DEMO{index:05d}" for index in range(self.customers)]
        customer_regions = {
            identifier: _weighted_choice(generator, REGIONS)
            for identifier in customer_identifiers
        }

        order_sequence = 0
        return_sequence = 0

        for month_index, month_start in enumerate(self._months()):
            # Growth with a seasonal bump in the two months before December,
            # so the series has trend and seasonality for the forecaster to
            # find, and growth accounting has months that move in both
            # directions.
            seasonal = 1.6 if month_start.month in (11, 12) else 1.0
            transactions = int((60 + month_index * 4) * seasonal)

            # Only customers acquired by this month can buy in it.
            available = customer_identifiers[
                : max(20, int(self.customers * (month_index + 1) / self.months))
            ]

            for _ in range(transactions):
                order_sequence += 1
                order_number = f"DEMO{order_sequence:06d}"
                ordered_at = _random_moment(generator, month_start)

                anonymous = generator.random() < ANONYMOUS_RATE
                customer = None if anonymous else generator.choice(available)
                region = (
                    _weighted_choice(generator, REGIONS)
                    if customer is None
                    else customer_regions[customer]
                )

                lines = self._basket(generator, codes, affinity)
                sold: list[tuple[str, int]] = []

                for code in lines:
                    description, price = catalogue[code]
                    quantity = generator.choice((1, 1, 2, 2, 3, 4, 6, 12))
                    sold.append((code, quantity))
                    yield CanonicalRecord(
                        order_number=order_number,
                        ordered_at=ordered_at,
                        stock_code=code,
                        quantity=quantity,
                        unit_price=price,
                        description=description,
                        customer_identifier=customer,
                        region_name=region,
                    )

                if generator.random() >= RETURN_RATE:
                    continue

                # A return is its own transaction, reversing one line of the
                # sale a few days later. The ingestion service reads a
                # transaction whose lines are all negative as a return, so the
                # sign is all that marks it.
                return_sequence += 1
                code, quantity = generator.choice(sold)
                description, price = catalogue[code]
                # Clamped inside the window, so a refund from the final month
                # does not spill into the partial current one and show up as a
                # month of nothing but refunds.
                returned_at = min(
                    ordered_at + timedelta(days=generator.randint(1, 21)),
                    self.end - timedelta(seconds=1),
                )
                yield CanonicalRecord(
                    order_number=f"CDEMO{return_sequence:06d}",
                    ordered_at=returned_at,
                    stock_code=code,
                    quantity=-quantity,
                    unit_price=price,
                    description=description,
                    customer_identifier=customer,
                    region_name=region,
                )

        logger.info(
            "demo_stream_complete",
            seed=self.seed,
            orders=order_sequence,
            returns=return_sequence,
        )

    def _months(self) -> list[datetime]:
        """First moment of each month in the generated window.

        Returns:
            Month starts in ascending order, `self.months` of them, the last
            one being the month before `self.end`.
        """
        months: list[datetime] = []
        cursor = self.end
        for _ in range(self.months):
            cursor = _previous_month(cursor)
            months.append(cursor)
        return list(reversed(months))

    def _basket(
        self,
        generator: random.Random,
        codes: list[str],
        affinity: dict[str, str],
    ) -> list[str]:
        """Choose the distinct products of one transaction.

        Args:
            generator: Seeded source of randomness.
            codes: Every stock code in the catalogue.
            affinity: Partner code for each code in `AFFINITY_PAIRS`.

        Returns:
            Between one and six distinct stock codes.
        """
        size = generator.choice((1, 2, 2, 3, 3, 4, 5, 6))
        basket: list[str] = []

        while len(basket) < size:
            code = generator.choice(codes)
            if code in basket:
                continue
            basket.append(code)

            # Pull in the partner most of the time, which is what makes the
            # pair's confidence and lift stand out from the popularity of
            # either product on its own.
            partner = affinity.get(code)
            if partner and partner not in basket and generator.random() < 0.7:
                basket.append(partner)

        return basket[:size] if len(basket) > size else basket


def _affinity_map() -> dict[str, str]:
    """Expand `AFFINITY_PAIRS` into a lookup in both directions.

    Returns:
        Partner stock code for each code that has one.
    """
    mapping: dict[str, str] = {}
    for left, right in AFFINITY_PAIRS:
        mapping[left] = right
        mapping[right] = left
    return mapping


def _weighted_choice(
    generator: random.Random, options: tuple[tuple[str, int], ...]
) -> str:
    """Pick one option in proportion to its weight.

    Args:
        generator: Seeded source of randomness.
        options: Pairs of value and relative weight.

    Returns:
        The chosen value.
    """
    population = [value for value, _weight in options]
    weights = [weight for _value, weight in options]
    return generator.choices(population, weights=weights, k=1)[0]


def _random_moment(generator: random.Random, month_start: datetime) -> datetime:
    """Pick a business-hours moment inside a month.

    Weekends are thinned rather than excluded, so the weekday breakdown has a
    visible shape instead of two empty columns.

    Args:
        generator: Seeded source of randomness.
        month_start: First moment of the month to place the transaction in.

    Returns:
        A timestamp within the month.
    """
    days = (_next_month(month_start) - month_start).days
    for _ in range(4):
        day = generator.randrange(days)
        moment = month_start + timedelta(days=day)
        if moment.weekday() < 5 or generator.random() < 0.3:
            break
    return moment + timedelta(
        hours=generator.randint(8, 18),
        minutes=generator.randrange(60),
    )


def _start_of_current_month() -> datetime:
    """First moment of the month the clock is currently in.

    Returns:
        A naive UTC timestamp, matching how `ordered_at` is stored.
    """
    now = datetime.now(UTC).replace(tzinfo=None)
    return now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)


def _next_month(moment: datetime) -> datetime:
    """First moment of the month after the given one.

    Args:
        moment: Any moment inside the reference month.

    Returns:
        The following month's first moment.
    """
    if moment.month == 12:
        return moment.replace(year=moment.year + 1, month=1, day=1)
    return moment.replace(month=moment.month + 1, day=1)


def _previous_month(moment: datetime) -> datetime:
    """First moment of the month before the given one.

    Args:
        moment: Any moment inside the reference month.

    Returns:
        The preceding month's first moment.
    """
    first = moment.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    return (first - timedelta(days=1)).replace(day=1)
