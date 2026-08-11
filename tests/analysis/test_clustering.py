"""Unit tests for nested clustering.

The fixtures below carry obvious, deliberately separated structure, so a
correct implementation has to recover groups that are identifiable by eye.
"""

from __future__ import annotations

import pytest

from app.analysis.clustering import InvalidClusteringParametersError
from app.analysis.clustering import flatten
from app.analysis.clustering import nested_partition
from app.analysis.clustering import partition
from app.analysis.clustering import summarise


def _two_obvious_groups() -> list[dict[str, object]]:
    """Build eight rows forming two well-separated groups.

    Returns:
        Feature rows with a "key", "revenue" and "orders".
    """
    low = [
        {"key": f"low-{index}", "revenue": 10.0 + index, "orders": 1 + index * 0.1}
        for index in range(4)
    ]
    high = [
        {"key": f"high-{index}", "revenue": 500.0 + index, "orders": 50 + index * 0.1}
        for index in range(4)
    ]
    return [*low, *high]


class TestPartition:
    """Tests for a single clustering pass."""

    def test_recovers_two_obvious_groups(self) -> None:
        """Well-separated data should be split along the obvious boundary.

        Returns:
            None.
        """
        result = partition(_two_obvious_groups(), ["revenue", "orders"])

        assert result.chosen_k == 2
        assert len(result.clusters) == 2

        grouped = [set(cluster.members) for cluster in result.clusters]
        expected_low = {f"low-{index}" for index in range(4)}
        expected_high = {f"high-{index}" for index in range(4)}
        assert expected_low in grouped
        assert expected_high in grouped

    def test_silhouette_is_high_for_separated_data(self) -> None:
        """A clean split should score close to one.

        Returns:
            None.
        """
        result = partition(_two_obvious_groups(), ["revenue", "orders"])

        assert result.silhouette is not None
        assert result.silhouette > 0.8

    def test_scores_are_reported_per_candidate_k(self) -> None:
        """Every evaluated k should be reported, for the thesis to tabulate.

        Returns:
            None.
        """
        result = partition(
            _two_obvious_groups(), ["revenue", "orders"], k_range=(2, 3, 4)
        )

        assert set(result.scores) == {2, 3, 4}
        # The chosen k must be the best-scoring one.
        assert result.chosen_k == max(result.scores, key=lambda k: result.scores[k])

    def test_features_are_standardised_before_clustering(self) -> None:
        """A large-scale feature must not dominate purely through its units.

        Returns:
            None.
        """
        # "revenue" spans thousands, "rate" spans hundredths, and the real
        # structure lives entirely in "rate". Without standardisation k-means
        # would cluster on revenue noise and miss it.
        rows = [
            {"key": "a", "revenue": 1000.0, "rate": 0.01},
            {"key": "b", "revenue": 1001.0, "rate": 0.02},
            {"key": "c", "revenue": 1002.0, "rate": 0.01},
            {"key": "d", "revenue": 1003.0, "rate": 0.02},
            {"key": "e", "revenue": 1004.0, "rate": 0.90},
            {"key": "f", "revenue": 1005.0, "rate": 0.91},
            {"key": "g", "revenue": 1006.0, "rate": 0.90},
            {"key": "h", "revenue": 1007.0, "rate": 0.91},
        ]

        result = partition(rows, ["revenue", "rate"], k_range=(2,))

        grouped = [set(cluster.members) for cluster in result.clusters]
        assert {"a", "b", "c", "d"} in grouped
        assert {"e", "f", "g", "h"} in grouped

    def test_clusters_are_ordered_by_size(self) -> None:
        """The largest cluster is labelled first, keeping labels discussable.

        Returns:
            None.
        """
        rows = [
            *[
                {"key": f"many-{index}", "revenue": 10.0 + index, "orders": 1.0}
                for index in range(6)
            ],
            *[
                {"key": f"few-{index}", "revenue": 900.0 + index, "orders": 90.0}
                for index in range(2)
            ],
        ]

        result = partition(rows, ["revenue", "orders"], k_range=(2,))

        sizes = [cluster.size for cluster in result.clusters]
        assert sizes == sorted(sizes, reverse=True)
        assert result.clusters[0].label == "1"

    def test_feature_means_describe_each_cluster(self) -> None:
        """Each node should carry the means that characterise it.

        Returns:
            None.
        """
        result = partition(_two_obvious_groups(), ["revenue", "orders"], k_range=(2,))

        for cluster in result.clusters:
            assert set(cluster.feature_means) == {"revenue", "orders"}

        means = sorted(cluster.feature_means["revenue"] for cluster in result.clusters)
        assert means[0] < 100
        assert means[1] > 400

    def test_results_are_reproducible(self) -> None:
        """A fixed seed must give identical partitions across runs.

        Returns:
            None.
        """
        first = partition(_two_obvious_groups(), ["revenue", "orders"])
        second = partition(_two_obvious_groups(), ["revenue", "orders"])

        assert [cluster.members for cluster in first.clusters] == [
            cluster.members for cluster in second.clusters
        ]

    def test_too_few_rows_form_a_single_cluster(self) -> None:
        """Three rows cannot support a partition, so none is invented.

        Returns:
            None.
        """
        rows = [
            {"key": "a", "revenue": 1.0, "orders": 1.0},
            {"key": "b", "revenue": 2.0, "orders": 2.0},
            {"key": "c", "revenue": 3.0, "orders": 3.0},
        ]

        result = partition(rows, ["revenue", "orders"])

        assert result.chosen_k == 1
        assert len(result.clusters) == 1
        assert result.clusters[0].size == 3
        assert result.silhouette is None

    def test_empty_input_returns_no_clusters(self) -> None:
        """No rows should return cleanly rather than raise.

        Returns:
            None.
        """
        result = partition([], ["revenue"])

        assert result.clusters == []
        assert result.chosen_k is None

    def test_missing_feature_is_rejected(self) -> None:
        """A row lacking a requested feature should raise a clear error.

        Returns:
            None.
        """
        rows = [{"key": "a", "revenue": 1.0}, {"key": "b", "revenue": 2.0}]

        with pytest.raises(InvalidClusteringParametersError, match="missing"):
            partition(rows, ["revenue", "orders"])

    def test_non_numeric_feature_is_rejected(self) -> None:
        """A non-numeric value should raise here, not inside scikit-learn.

        Returns:
            None.
        """
        rows = [
            {"key": "a", "revenue": "not a number", "orders": 1.0},
            {"key": "b", "revenue": 2.0, "orders": 2.0},
        ]

        with pytest.raises(InvalidClusteringParametersError, match="not numeric"):
            partition(rows, ["revenue", "orders"])

    def test_no_features_is_rejected(self) -> None:
        """Clustering on nothing is a caller error.

        Returns:
            None.
        """
        with pytest.raises(InvalidClusteringParametersError):
            partition(_two_obvious_groups(), [])

    def test_missing_values_are_treated_as_zero(self) -> None:
        """A null feature should not abort an otherwise usable run.

        Returns:
            None.
        """
        rows = _two_obvious_groups()
        rows[0]["revenue"] = None

        result = partition(rows, ["revenue", "orders"], k_range=(2,))

        assert result.chosen_k == 2


class TestNestedPartition:
    """Tests for the two-level tree."""

    def test_second_level_clusters_within_each_first_level_cluster(self) -> None:
        """Each first-level cluster gets its own sub-partition.

        Returns:
            None.
        """
        regions = [
            {"key": "north", "revenue": 10.0, "orders": 1.0},
            {"key": "south", "revenue": 11.0, "orders": 1.1},
            {"key": "east", "revenue": 900.0, "orders": 90.0},
            {"key": "west", "revenue": 901.0, "orders": 91.0},
        ]

        def customers(prefix: str) -> list[dict[str, object]]:
            return [
                *[
                    {
                        "key": f"{prefix}-loyal-{index}",
                        "recency": 1.0 + index,
                        "frequency": 20.0,
                        "monetary": 500.0,
                    }
                    for index in range(4)
                ],
                *[
                    {
                        "key": f"{prefix}-lapsed-{index}",
                        "recency": 300.0 + index,
                        "frequency": 1.0,
                        "monetary": 10.0,
                    }
                    for index in range(4)
                ],
            ]

        second_level = {name["key"]: customers(str(name["key"])) for name in regions}

        result = nested_partition(
            regions,
            ["revenue", "orders"],
            second_level,  # type: ignore[arg-type]
            ["recency", "frequency", "monetary"],
            k_range=(2,),
        )

        assert len(result.clusters) == 2
        for cluster in result.clusters:
            assert cluster.level == 1
            assert cluster.children
            for child in cluster.children:
                assert child.level == 2
                assert child.label.startswith(f"{cluster.label}.")

    def test_sub_clusters_separate_loyal_from_lapsed(self) -> None:
        """The RFM pass should recover the behavioural split.

        Returns:
            None.
        """
        regions = [
            {"key": "a", "revenue": 10.0, "orders": 1.0},
            {"key": "b", "revenue": 11.0, "orders": 1.1},
            {"key": "c", "revenue": 900.0, "orders": 90.0},
            {"key": "d", "revenue": 901.0, "orders": 91.0},
        ]
        pooled = [
            *[
                {
                    "key": f"loyal-{index}",
                    "recency": 1.0,
                    "frequency": 20.0,
                    "monetary": 500.0,
                }
                for index in range(4)
            ],
            *[
                {
                    "key": f"lapsed-{index}",
                    "recency": 300.0,
                    "frequency": 1.0,
                    "monetary": 10.0,
                }
                for index in range(4)
            ],
        ]

        result = nested_partition(
            regions,
            ["revenue", "orders"],
            {"a": pooled, "b": [], "c": [], "d": []},  # type: ignore[arg-type]
            ["recency", "frequency", "monetary"],
            k_range=(2,),
        )

        owner = next(cluster for cluster in result.clusters if "a" in cluster.members)
        grouped = [set(child.members) for child in owner.children]

        assert {f"loyal-{index}" for index in range(4)} in grouped
        assert {f"lapsed-{index}" for index in range(4)} in grouped

    def test_cluster_without_second_level_rows_has_no_children(self) -> None:
        """A group with nothing to sub-cluster stays a leaf.

        Returns:
            None.
        """
        regions = [
            {"key": "a", "revenue": 10.0, "orders": 1.0},
            {"key": "b", "revenue": 11.0, "orders": 1.1},
            {"key": "c", "revenue": 900.0, "orders": 90.0},
            {"key": "d", "revenue": 901.0, "orders": 91.0},
        ]

        result = nested_partition(
            regions,
            ["revenue", "orders"],
            {},
            ["recency"],
            k_range=(2,),
        )

        assert all(cluster.children == [] for cluster in result.clusters)

    def test_flatten_walks_the_whole_tree(self) -> None:
        """Flattening should yield parents and children alike.

        Returns:
            None.
        """
        regions = [
            {"key": "a", "revenue": 10.0, "orders": 1.0},
            {"key": "b", "revenue": 11.0, "orders": 1.1},
            {"key": "c", "revenue": 900.0, "orders": 90.0},
            {"key": "d", "revenue": 901.0, "orders": 91.0},
        ]
        pooled = [
            {"key": f"customer-{index}", "recency": float(index * 100)}
            for index in range(6)
        ]

        result = nested_partition(
            regions,
            ["revenue", "orders"],
            {"a": pooled, "b": [], "c": [], "d": []},  # type: ignore[arg-type]
            ["recency"],
            k_range=(2,),
        )

        walked = flatten(result.clusters)

        assert len(walked) > len(result.clusters)
        assert {node.level for node in walked} == {1, 2}


class TestSummarise:
    """Tests for the summary helper."""

    def test_summary_reports_scores_and_nodes(self) -> None:
        """The summary should carry the chosen k and every node.

        Returns:
            None.
        """
        result = partition(_two_obvious_groups(), ["revenue", "orders"])

        summary = summarise(result)

        assert summary["chosen_k"] == 2
        assert summary["silhouette"] is not None
        assert len(summary["clusters"]) == 2
        assert set(summary["scores"]) == set(result.scores)
