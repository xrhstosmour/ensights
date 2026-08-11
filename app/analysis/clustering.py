"""Nested clustering over commerce features.

Implements the structure the thesis requires: cluster first on the parameters
that carry the most meaning, region and time, then cluster again *within* each
resulting group on additional parameters, producing a tree whose every node can
be interrogated separately.

The number of clusters is not fixed in advance. For each candidate k the
silhouette coefficient \\parencite{rousseeuw1987silhouettes} is computed and
the best-scoring k is kept, so the partition is chosen by the data rather than
by assumption.

This module holds no database or framework concerns; it takes feature rows and
returns a tree.
"""

from __future__ import annotations

from dataclasses import dataclass
from dataclasses import field
from typing import TYPE_CHECKING
from typing import Any

from app.core.logging import get_logger

if TYPE_CHECKING:
    from collections.abc import Mapping
    from collections.abc import Sequence

logger = get_logger("analysis.clustering")

# A silhouette score needs at least two clusters, and a cluster needs at least
# one member, so k can never exceed the number of rows minus one.
MINIMUM_ROWS_TO_CLUSTER = 4
DEFAULT_K_RANGE = (2, 3, 4, 5, 6)


class ClusteringError(Exception):
    """Base class for clustering failures."""


class InvalidClusteringParametersError(ClusteringError):
    """Raised when the requested parameters cannot produce a partition."""


@dataclass
class ClusterNode:
    """One cluster, possibly containing sub-clusters.

    Attributes:
        label: Human-readable identifier, for example "1.2"
        level: Depth in the tree, starting at 1
        size: Number of members
        members: Keys of the rows assigned to this cluster
        feature_means: Mean of each clustering feature within the cluster
        silhouette: Silhouette score of the partition this cluster belongs to,
            shared by its siblings, or None when scoring was impossible
        children: Sub-clusters formed within this cluster
    """

    label: str
    level: int
    size: int
    members: list[str] = field(default_factory=list)
    feature_means: dict[str, float] = field(default_factory=dict)
    silhouette: float | None = None
    children: list[ClusterNode] = field(default_factory=list)


@dataclass
class PartitionResult:
    """One flat clustering pass.

    Attributes:
        clusters: The clusters found
        silhouette: Silhouette score of the chosen partition
        chosen_k: Number of clusters selected
        scores: Silhouette score per candidate k, for the thesis to report
    """

    clusters: list[ClusterNode] = field(default_factory=list)
    silhouette: float | None = None
    chosen_k: int | None = None
    scores: dict[int, float] = field(default_factory=dict)


def _matrix(
    rows: Sequence[dict[str, Any]], features: Sequence[str]
) -> tuple[list[str], list[list[float]]]:
    """Extract keys and a numeric matrix from feature rows.

    Args:
        rows: Feature rows, each carrying a "key" plus the named features.
        features: Feature names to extract.

    Returns:
        The row keys and the corresponding numeric matrix.

    Raises:
        InvalidClusteringParametersError: If a feature is missing or is not
            numeric, which would otherwise fail deep inside scikit-learn.
    """
    keys: list[str] = []
    matrix: list[list[float]] = []

    for index, row in enumerate(rows):
        key = str(row.get("key", index))
        vector: list[float] = []
        for name in features:
            if name not in row:
                message = f"Row {key!r} is missing the feature {name!r}"
                raise InvalidClusteringParametersError(message)
            value = row[name]
            if value is None:
                value = 0
            try:
                vector.append(float(value))
            except (TypeError, ValueError) as error:
                message = f"Feature {name!r} on row {key!r} is not numeric: {value!r}"
                raise InvalidClusteringParametersError(message) from error
        keys.append(key)
        matrix.append(vector)

    return keys, matrix


def partition(
    rows: Sequence[dict[str, Any]],
    features: Sequence[str],
    k_range: Sequence[int] = DEFAULT_K_RANGE,
    label_prefix: str = "",
    level: int = 1,
    random_state: int = 42,
) -> PartitionResult:
    """Cluster rows on the given features, choosing k by silhouette.

    Features are standardised before clustering. Without it, a feature
    measured in currency would dominate one measured in counts purely because
    of its scale, and k-means would be clustering on units rather than on
    behaviour.

    Args:
        rows: Feature rows, each carrying a "key" plus the named features.
        features: Feature names to cluster on.
        k_range: Candidate cluster counts to evaluate.
        label_prefix: Prefix for child labels, used when nesting.
        level: Depth to record on the resulting nodes.
        random_state: Seed, fixed so runs are reproducible for the thesis.

    Returns:
        The clusters found, with the silhouette scores that chose them.

    Raises:
        InvalidClusteringParametersError: If no features are given or a
            feature is unusable.
    """
    if not features:
        message = "At least one feature is required to cluster on"
        raise InvalidClusteringParametersError(message)

    result = PartitionResult()
    if not rows:
        return result

    keys, matrix = _matrix(rows, features)

    # Too few rows to partition meaningfully: report them as a single cluster
    # rather than inventing structure that the data cannot support.
    if len(rows) < MINIMUM_ROWS_TO_CLUSTER:
        result.clusters = [
            _node(f"{label_prefix}1", level, keys, matrix, features, None)
        ]
        result.chosen_k = 1
        return result

    from sklearn.cluster import KMeans
    from sklearn.metrics import silhouette_score
    from sklearn.preprocessing import StandardScaler

    scaled = StandardScaler().fit_transform(matrix)

    candidates = [k for k in k_range if 2 <= k <= len(rows) - 1]
    if not candidates:
        result.clusters = [
            _node(f"{label_prefix}1", level, keys, matrix, features, None)
        ]
        result.chosen_k = 1
        return result

    best_k: int | None = None
    best_score: float | None = None
    best_labels: Any = None

    for k in candidates:
        model = KMeans(n_clusters=k, random_state=random_state, n_init=10)
        labels = model.fit_predict(scaled)
        # An assignment that collapsed to fewer than k groups cannot be scored.
        if len(set(labels)) < 2:
            continue
        score = float(silhouette_score(scaled, labels))
        result.scores[k] = score
        if best_score is None or score > best_score:
            best_k, best_score, best_labels = k, score, labels

    if best_labels is None:
        result.clusters = [
            _node(f"{label_prefix}1", level, keys, matrix, features, None)
        ]
        result.chosen_k = 1
        return result

    grouped: dict[int, list[int]] = {}
    for index, label in enumerate(best_labels):
        grouped.setdefault(int(label), []).append(index)

    result.clusters = [
        _node(
            f"{label_prefix}{position}",
            level,
            [keys[index] for index in indexes],
            [matrix[index] for index in indexes],
            features,
            best_score,
        )
        # Sorted by size so the largest cluster is always "1", which keeps
        # labels stable enough to discuss across runs.
        for position, (_, indexes) in enumerate(
            sorted(grouped.items(), key=lambda item: len(item[1]), reverse=True),
            start=1,
        )
    ]
    result.silhouette = best_score
    result.chosen_k = best_k

    logger.info(
        "partition_complete",
        rows=len(rows),
        features=list(features),
        chosen_k=best_k,
        silhouette=best_score,
    )
    return result


def _node(
    label: str,
    level: int,
    keys: Sequence[str],
    matrix: Sequence[Sequence[float]],
    features: Sequence[str],
    silhouette: float | None,
) -> ClusterNode:
    """Build a cluster node with its feature means.

    Args:
        label: Node label.
        level: Depth in the tree.
        keys: Member keys.
        matrix: Member feature vectors.
        features: Feature names, in the matrix's column order.
        silhouette: Silhouette of the owning partition.

    Returns:
        The node.
    """
    means: dict[str, float] = {}
    if matrix:
        for column, name in enumerate(features):
            means[name] = sum(vector[column] for vector in matrix) / len(matrix)

    return ClusterNode(
        label=label,
        level=level,
        size=len(keys),
        members=list(keys),
        feature_means=means,
        silhouette=silhouette,
    )


def nested_partition(
    rows: Sequence[dict[str, Any]],
    first_level_features: Sequence[str],
    second_level_rows: Mapping[str, Sequence[dict[str, Any]]],
    second_level_features: Sequence[str],
    k_range: Sequence[int] = DEFAULT_K_RANGE,
    random_state: int = 42,
) -> PartitionResult:
    """Cluster once, then cluster again inside each resulting cluster.

    This is the tree the supervisor asked for: a first pass over the
    parameters that matter most, for example region and time, and a second
    pass within each group over additional parameters, for example RFM.

    Args:
        rows: First-level feature rows, each carrying a "key".
        first_level_features: Features for the first pass.
        second_level_rows: Second-level rows keyed by the first-level key they
            belong to, for example customers per region.
        second_level_features: Features for the second pass.
        k_range: Candidate cluster counts to evaluate at both levels.
        random_state: Seed, fixed so runs are reproducible.

    Returns:
        The first-level clusters, each carrying its sub-clusters.

    Raises:
        InvalidClusteringParametersError: If either feature list is unusable.
    """
    result = partition(
        rows,
        first_level_features,
        k_range=k_range,
        level=1,
        random_state=random_state,
    )

    for cluster in result.clusters:
        # Pool every second-level row belonging to any member of this cluster,
        # so the sub-clustering sees the group as a whole rather than one
        # member at a time.
        pooled: list[dict[str, Any]] = []
        for member in cluster.members:
            pooled.extend(second_level_rows.get(member, []))

        if not pooled:
            continue

        child = partition(
            pooled,
            second_level_features,
            k_range=k_range,
            label_prefix=f"{cluster.label}.",
            level=cluster.level + 1,
            random_state=random_state,
        )
        cluster.children = child.clusters

    return result


def flatten(clusters: Sequence[ClusterNode]) -> list[ClusterNode]:
    """Walk a cluster tree depth-first.

    Args:
        clusters: Roots to walk.

    Returns:
        Every node in the tree.
    """
    walked: list[ClusterNode] = []
    for cluster in clusters:
        walked.append(cluster)
        walked.extend(flatten(cluster.children))
    return walked


def summarise(result: PartitionResult) -> dict[str, Any]:
    """Summarise a partition for logging or a notebook.

    Args:
        result: The partition to summarise.

    Returns:
        The chosen k, its silhouette, the per-k scores and the node sizes.
    """
    return {
        "chosen_k": result.chosen_k,
        "silhouette": result.silhouette,
        "scores": {k: round(score, 4) for k, score in result.scores.items()},
        "clusters": [
            {
                "label": node.label,
                "level": node.level,
                "size": node.size,
                "silhouette": node.silhouette,
                "feature_means": {
                    name: round(value, 4) for name, value in node.feature_means.items()
                },
                "children": len(node.children),
            }
            for node in flatten(result.clusters)
        ],
    }
