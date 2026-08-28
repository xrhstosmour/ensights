"""Unit tests for the synthetic demo transaction source."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from app.ingestion.demo import CATALOGUE
from app.ingestion.demo import DemoDataAdapter
from app.repositories.analytics_repository import PRICE_BANDS
from app.repositories.analytics_repository import PRODUCT_CHARACTERISTICS

# Fixed window, so the assertions below do not move with the wall clock.
END = datetime(2026, 1, 1)


def _band(price: Decimal) -> str:
    """Label the band a price falls in, the way the endpoint does.

    Args:
        price: Unit price to classify.

    Returns:
        The matching band label, or "unknown" if no band claims it.
    """
    for label, lower, upper in PRICE_BANDS:
        if price >= lower and (upper is None or price < upper):
            return label
    return "unknown"


class TestDemoDataAdapter:
    """Tests for DemoDataAdapter.fetch()."""

    def test_is_deterministic_for_a_given_seed(self) -> None:
        """Two runs with the same seed should produce identical records.

        This is what lets a screenshot, a figure and a re-run of the demo
        agree, so it is asserted rather than assumed.

        Returns:
            None.
        """
        first = list(DemoDataAdapter(seed=7, months=3, customers=20, end=END).fetch())
        second = list(DemoDataAdapter(seed=7, months=3, customers=20, end=END).fetch())

        assert first == second
        assert first

    def test_a_different_seed_produces_different_records(self) -> None:
        """The seed should actually drive the generator.

        Returns:
            None.
        """
        first = list(DemoDataAdapter(seed=7, months=3, customers=20, end=END).fetch())
        second = list(DemoDataAdapter(seed=8, months=3, customers=20, end=END).fetch())

        assert first != second

    def test_covers_the_requested_window(self) -> None:
        """Records should span the requested months and stop before the end.

        Returns:
            None.
        """
        records = list(DemoDataAdapter(seed=7, months=6, customers=40, end=END).fetch())

        months = {
            (record.ordered_at.year, record.ordered_at.month) for record in records
        }
        assert len(months) == 6
        assert max(record.ordered_at for record in records) < END

    def test_yields_returns_as_negative_quantities(self) -> None:
        """Refunds should be present, and reverse a line that was sold.

        Returns:
            None.
        """
        records = list(
            DemoDataAdapter(seed=7, months=12, customers=60, end=END).fetch()
        )

        returns = [record for record in records if record.quantity < 0]
        assert returns
        assert all(record.order_number.startswith("CDEMO") for record in returns)
        assert all(record.unit_price > 0 for record in returns)

    def test_keeps_some_sales_anonymous(self) -> None:
        """A share of lines should carry no customer identifier.

        Roughly a quarter of the real dataset has none, and the
        customer-level analyses have to cope with that, so the demo data
        cannot be uniformly identified.

        Returns:
            None.
        """
        records = list(DemoDataAdapter(seed=7, months=6, customers=40, end=END).fetch())

        assert any(record.customer_identifier is None for record in records)
        assert any(record.customer_identifier is not None for record in records)

    def test_prices_are_positive_and_cover_every_band(self) -> None:
        """Every price band should be reachable, and none priced at zero.

        A zero or negative price is rejected by `classify_record`, so the
        catalogue must stay above it or lines would silently vanish.

        Returns:
            None.
        """
        prices = [Decimal(price) for _code, _description, price in CATALOGUE]

        assert all(price > 0 for price in prices)
        assert {_band(price) for price in prices} == {
            label for label, _lower, _upper in PRICE_BANDS
        }

    def test_descriptions_cover_every_characteristic(self) -> None:
        """No characteristic should be empty in the demo database.

        `sales-by-characteristic` reports "uncategorised" for a product that
        matches no keyword group, and a demo where every product lands there
        shows nothing.

        Returns:
            None.
        """
        descriptions = [description for _code, description, _price in CATALOGUE]

        matched = set()
        for characteristic, keywords in PRODUCT_CHARACTERISTICS:
            if any(
                keyword in description
                for description in descriptions
                for keyword in keywords
            ):
                matched.add(characteristic)

        assert matched == {
            characteristic for characteristic, _keywords in PRODUCT_CHARACTERISTICS
        }

    def test_baskets_hold_distinct_products(self) -> None:
        """A transaction should never repeat a stock code.

        Market basket mining treats a basket as a set, and a duplicated line
        would also break the natural key the ingestion service relies on.

        Returns:
            None.
        """
        records = list(DemoDataAdapter(seed=7, months=4, customers=30, end=END).fetch())

        baskets: dict[str, list[str]] = {}
        for record in records:
            baskets.setdefault(record.order_number, []).append(record.stock_code)

        for codes in baskets.values():
            assert len(codes) == len(set(codes))

    def test_source_name_marks_the_data_as_synthetic(self) -> None:
        """Provenance should never let demo data pass for the real dataset.

        Returns:
            None.
        """
        assert DemoDataAdapter(seed=7).source_name == "demo-synthetic-seed-7"
