"""Frequent itemset mining and association rule generation.

Implements the market-basket analysis the thesis requires, over baskets built
from order lines. Both classical algorithms are offered: Apriori
(\\cite{agrawal1994fast}) generates candidates level by level, FP-Growth
(\\cite{han2000mining}) builds a prefix tree and avoids candidate generation.
They produce identical itemsets for the same threshold, so the choice is one of
runtime rather than result, and the comparison is itself a thesis experiment.

This module holds no database or framework concerns; it takes baskets and
returns results.
"""

from __future__ import annotations

from dataclasses import dataclass
from dataclasses import field
from typing import TYPE_CHECKING
from typing import Any

from app.core.logging import get_logger

if TYPE_CHECKING:
    from collections.abc import Sequence

logger = get_logger("analysis.frequent_itemsets")

APRIORI = "apriori"
FPGROWTH = "fpgrowth"
ALGORITHMS = (APRIORI, FPGROWTH)


class FrequentItemsetError(Exception):
    """Base class for mining failures."""


class InvalidMiningParametersError(FrequentItemsetError):
    """Raised when the requested parameters cannot produce a result."""


@dataclass(frozen=True, slots=True)
class Itemset:
    """One frequent itemset.

    Attributes:
        items: Stock codes forming the set
        support: Fraction of baskets containing all of them
    """

    items: tuple[str, ...]
    support: float


@dataclass(frozen=True, slots=True)
class Rule:
    """One association rule.

    Attributes:
        antecedents: Stock codes on the left-hand side
        consequents: Stock codes on the right-hand side
        support: Fraction of baskets containing both sides
        confidence: Probability of the consequent given the antecedent
        lift: Confidence divided by the consequent's own support
    """

    antecedents: tuple[str, ...]
    consequents: tuple[str, ...]
    support: float
    confidence: float
    lift: float


@dataclass
class MiningResult:
    """Everything one mining run produced.

    Attributes:
        algorithm: Algorithm used
        minimum_support: Support threshold applied
        minimum_confidence: Confidence threshold applied to rules
        basket_count: Number of baskets mined
        itemsets: Frequent itemsets found
        rules: Association rules derived from them
    """

    algorithm: str
    minimum_support: float
    minimum_confidence: float
    basket_count: int
    itemsets: list[Itemset] = field(default_factory=list)
    rules: list[Rule] = field(default_factory=list)


def _validate(
    algorithm: str,
    minimum_support: float,
    minimum_confidence: float,
) -> None:
    """Reject parameters that cannot produce a meaningful result.

    Args:
        algorithm: Requested algorithm.
        minimum_support: Support threshold.
        minimum_confidence: Confidence threshold.

    Raises:
        InvalidMiningParametersError: If any parameter is out of range.
    """
    if algorithm not in ALGORITHMS:
        message = (
            f"Unknown algorithm {algorithm!r}, expected one of {', '.join(ALGORITHMS)}"
        )
        raise InvalidMiningParametersError(message)
    if not 0 < minimum_support <= 1:
        message = "Minimum support must fall in (0, 1]"
        raise InvalidMiningParametersError(message)
    if not 0 < minimum_confidence <= 1:
        message = "Minimum confidence must fall in (0, 1]"
        raise InvalidMiningParametersError(message)


def mine(
    baskets: Sequence[Sequence[str]],
    algorithm: str = FPGROWTH,
    minimum_support: float = 0.01,
    minimum_confidence: float = 0.3,
    maximum_itemset_size: int | None = None,
) -> MiningResult:
    """Mine frequent itemsets and association rules from baskets.

    Args:
        baskets: One sequence of stock codes per transaction.
        algorithm: Either "apriori" or "fpgrowth".
        minimum_support: Minimum fraction of baskets an itemset must appear in.
        minimum_confidence: Minimum confidence for a rule to be reported.
        maximum_itemset_size: Optional cap on itemset size, which bounds
            runtime on dense data.

    Returns:
        The itemsets and rules found.

    Raises:
        InvalidMiningParametersError: If the parameters are out of range.
    """
    _validate(algorithm, minimum_support, minimum_confidence)

    # Imported here rather than at module scope: these pull in scipy and
    # scikit-learn, and nothing should pay that import cost on a web request
    # that never mines anything.
    import pandas as pd
    from mlxtend.frequent_patterns import apriori as run_apriori
    from mlxtend.frequent_patterns import association_rules
    from mlxtend.frequent_patterns import fpgrowth as run_fpgrowth
    from mlxtend.preprocessing import TransactionEncoder

    # Duplicate lines of the same product within one basket carry no extra
    # information for co-occurrence, and an unsorted basket produces the same
    # itemsets, so both are normalised away before encoding.
    cleaned = [sorted(set(basket)) for basket in baskets if basket]

    result = MiningResult(
        algorithm=algorithm,
        minimum_support=minimum_support,
        minimum_confidence=minimum_confidence,
        basket_count=len(cleaned),
    )
    if not cleaned:
        logger.info("mining_skipped_no_baskets")
        return result

    encoder = TransactionEncoder()
    encoded = encoder.fit(cleaned).transform(cleaned)
    frame = pd.DataFrame(encoded, columns=encoder.columns_)

    miner = run_apriori if algorithm == APRIORI else run_fpgrowth
    itemsets = miner(
        frame,
        min_support=minimum_support,
        use_colnames=True,
        max_len=maximum_itemset_size,
    )

    if itemsets.empty:
        logger.info(
            "mining_found_no_itemsets",
            algorithm=algorithm,
            minimum_support=minimum_support,
            baskets=len(cleaned),
        )
        return result

    result.itemsets = [
        Itemset(items=tuple(sorted(row.itemsets)), support=float(row.support))
        for row in itemsets.itertuples()
    ]

    # Rules need at least one two-item set to exist; asking mlxtend for rules
    # from singletons alone raises rather than returning nothing.
    if itemsets["itemsets"].map(len).max() < 2:
        logger.info("mining_found_no_multi_item_sets", algorithm=algorithm)
        return result

    rules = association_rules(
        itemsets, metric="confidence", min_threshold=minimum_confidence
    )
    result.rules = [
        Rule(
            antecedents=tuple(sorted(row.antecedents)),
            consequents=tuple(sorted(row.consequents)),
            support=float(row.support),
            confidence=float(row.confidence),
            lift=float(row.lift),
        )
        for row in rules.itertuples()
    ]
    result.rules.sort(key=lambda rule: rule.lift, reverse=True)

    logger.info(
        "mining_complete",
        algorithm=algorithm,
        baskets=len(cleaned),
        itemsets=len(result.itemsets),
        rules=len(result.rules),
    )
    return result


def summarise(result: MiningResult, top: int = 10) -> dict[str, Any]:
    """Summarise a run for logging or a notebook.

    Args:
        result: The run to summarise.
        top: How many of the strongest rules to include.

    Returns:
        Counts and the strongest rules by lift.
    """
    return {
        "algorithm": result.algorithm,
        "minimum_support": result.minimum_support,
        "minimum_confidence": result.minimum_confidence,
        "baskets": result.basket_count,
        "itemsets": len(result.itemsets),
        "rules": len(result.rules),
        "strongest": [
            {
                "antecedents": list(rule.antecedents),
                "consequents": list(rule.consequents),
                "support": round(rule.support, 4),
                "confidence": round(rule.confidence, 4),
                "lift": round(rule.lift, 4),
            }
            for rule in result.rules[:top]
        ],
    }
