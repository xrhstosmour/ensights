"""Unit tests for frequent itemset mining.

The baskets below are small enough that every support, confidence and lift
asserted here can be worked out by hand, which is the point: a mining result
that only agrees with itself proves nothing.
"""

from __future__ import annotations

import pytest

from app.analysis.frequent_itemsets import APRIORI
from app.analysis.frequent_itemsets import FPGROWTH
from app.analysis.frequent_itemsets import InvalidMiningParametersError
from app.analysis.frequent_itemsets import mine
from app.analysis.frequent_itemsets import summarise

# Five baskets. Bread and butter appear together in four of them, milk in
# three, and jam only once.
BASKETS = [
    ["bread", "butter", "milk"],
    ["bread", "butter"],
    ["bread", "butter", "milk"],
    ["bread", "butter", "milk", "jam"],
    ["bread"],
]


class TestMining:
    """Tests for the mining entry point."""

    def test_single_item_supports_are_exact(self) -> None:
        """Support of a single item is its share of baskets.

        Returns:
            None.
        """
        result = mine(BASKETS, minimum_support=0.1, minimum_confidence=0.1)

        supports = {
            itemset.items[0]: itemset.support
            for itemset in result.itemsets
            if len(itemset.items) == 1
        }

        assert supports["bread"] == pytest.approx(1.0)
        assert supports["butter"] == pytest.approx(0.8)
        assert supports["milk"] == pytest.approx(0.6)
        assert supports["jam"] == pytest.approx(0.2)

    def test_pair_support_is_exact(self) -> None:
        """Bread and butter co-occur in four of five baskets.

        Returns:
            None.
        """
        result = mine(BASKETS, minimum_support=0.1, minimum_confidence=0.1)

        pair = next(
            itemset
            for itemset in result.itemsets
            if itemset.items == ("bread", "butter")
        )

        assert pair.support == pytest.approx(0.8)

    def test_support_threshold_excludes_rare_items(self) -> None:
        """An item below the threshold should not be reported at all.

        Returns:
            None.
        """
        result = mine(BASKETS, minimum_support=0.5, minimum_confidence=0.1)

        items = {item for itemset in result.itemsets for item in itemset.items}

        assert "jam" not in items
        assert "bread" in items

    def test_rule_confidence_and_lift_are_exact(self) -> None:
        """Butter implies bread with certainty, so lift is exactly one.

        Returns:
            None.
        """
        result = mine(BASKETS, minimum_support=0.1, minimum_confidence=0.1)

        rule = next(
            candidate
            for candidate in result.rules
            if candidate.antecedents == ("butter",)
            and candidate.consequents == ("bread",)
        )

        # Every basket with butter also has bread: confidence is 1.0. Bread is
        # in every basket, so its support is 1.0 and lift is 1.0 / 1.0.
        assert rule.confidence == pytest.approx(1.0)
        assert rule.lift == pytest.approx(1.0)

    def test_lift_above_one_signals_real_association(self) -> None:
        """Milk implies butter more often than butter's own frequency.

        Returns:
            None.
        """
        result = mine(BASKETS, minimum_support=0.1, minimum_confidence=0.1)

        rule = next(
            candidate
            for candidate in result.rules
            if candidate.antecedents == ("milk",)
            and candidate.consequents == ("butter",)
        )

        # All three milk baskets contain butter, so confidence is 1.0, while
        # butter's own support is 0.8: lift is 1.25.
        assert rule.confidence == pytest.approx(1.0)
        assert rule.lift == pytest.approx(1.25)

    def test_confidence_threshold_filters_rules(self) -> None:
        """Rules below the confidence threshold should not be returned.

        Returns:
            None.
        """
        result = mine(BASKETS, minimum_support=0.1, minimum_confidence=0.95)

        assert result.rules
        assert all(rule.confidence >= 0.95 for rule in result.rules)

    def test_rules_are_sorted_by_lift(self) -> None:
        """The strongest association should come first.

        Returns:
            None.
        """
        result = mine(BASKETS, minimum_support=0.1, minimum_confidence=0.1)

        lifts = [rule.lift for rule in result.rules]

        assert lifts == sorted(lifts, reverse=True)

    def test_both_algorithms_agree(self) -> None:
        """Apriori and FP-Growth differ in runtime, not in results.

        Returns:
            None.
        """
        apriori = mine(BASKETS, algorithm=APRIORI, minimum_support=0.2)
        fpgrowth = mine(BASKETS, algorithm=FPGROWTH, minimum_support=0.2)

        def normalise(result: object) -> set[tuple[tuple[str, ...], float]]:
            return {
                (itemset.items, round(itemset.support, 6))
                for itemset in result.itemsets  # type: ignore[attr-defined]
            }

        assert normalise(apriori) == normalise(fpgrowth)

    def test_duplicate_items_within_a_basket_are_collapsed(self) -> None:
        """A product listed twice on one invoice is still one occurrence.

        Returns:
            None.
        """
        duplicated = mine(
            [["bread", "bread", "butter"], ["bread", "butter"]],
            minimum_support=0.5,
            minimum_confidence=0.5,
        )
        deduplicated = mine(
            [["bread", "butter"], ["bread", "butter"]],
            minimum_support=0.5,
            minimum_confidence=0.5,
        )

        assert len(duplicated.itemsets) == len(deduplicated.itemsets)
        assert duplicated.basket_count == deduplicated.basket_count

    def test_maximum_itemset_size_is_respected(self) -> None:
        """Capping the size bounds runtime on dense baskets.

        Returns:
            None.
        """
        result = mine(BASKETS, minimum_support=0.1, maximum_itemset_size=2)

        assert result.itemsets
        assert max(len(itemset.items) for itemset in result.itemsets) == 2

    def test_empty_input_returns_an_empty_result(self) -> None:
        """No baskets should return cleanly rather than raise.

        Returns:
            None.
        """
        result = mine([])

        assert result.basket_count == 0
        assert result.itemsets == []
        assert result.rules == []

    def test_single_item_baskets_produce_no_rules(self) -> None:
        """Rules need co-occurrence, which one-item baskets cannot show.

        Returns:
            None.
        """
        result = mine([["bread"], ["bread"], ["milk"]], minimum_support=0.1)

        assert result.itemsets
        assert result.rules == []

    def test_threshold_above_every_support_returns_nothing(self) -> None:
        """An unreachable threshold returns empty rather than raising.

        Returns:
            None.
        """
        result = mine(BASKETS, minimum_support=1.0, minimum_confidence=0.5)

        # Only bread appears in every basket, so no pair can survive.
        assert all(len(itemset.items) == 1 for itemset in result.itemsets)
        assert result.rules == []

    @pytest.mark.parametrize(
        ("algorithm", "support", "confidence"),
        [
            ("bogus", 0.1, 0.1),
            (FPGROWTH, 0.0, 0.1),
            (FPGROWTH, 1.5, 0.1),
            (FPGROWTH, 0.1, 0.0),
            (FPGROWTH, 0.1, 1.5),
        ],
    )
    def test_invalid_parameters_are_rejected(
        self, algorithm: str, support: float, confidence: float
    ) -> None:
        """Out-of-range parameters should raise before any work happens.

        Args:
            algorithm: Algorithm name under test.
            support: Support threshold under test.
            confidence: Confidence threshold under test.

        Returns:
            None.
        """
        with pytest.raises(InvalidMiningParametersError):
            mine(
                BASKETS,
                algorithm=algorithm,
                minimum_support=support,
                minimum_confidence=confidence,
            )


class TestSummarise:
    """Tests for the run summary helper."""

    def test_summary_reports_counts_and_strongest_rules(self) -> None:
        """The summary should carry the parameters and the top rules.

        Returns:
            None.
        """
        result = mine(BASKETS, minimum_support=0.1, minimum_confidence=0.1)

        summary = summarise(result, top=3)

        assert summary["baskets"] == 5
        assert summary["itemsets"] == len(result.itemsets)
        assert len(summary["strongest"]) == 3
        assert summary["strongest"][0]["lift"] >= summary["strongest"][1]["lift"]
